"""Gerenciamento de clientes WireGuard VPN."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Tuple

import typer

from raijin_server.utils import ExecutionContext, logger, require_root, run_cmd, write_file

WIREGUARD_DIR = Path("/etc/wireguard")
WG0_CONF = WIREGUARD_DIR / "wg0.conf"
CLIENTS_DIR = WIREGUARD_DIR / "clients"


def _generate_keypair() -> Tuple[str, str]:
    """Gera par de chaves WireGuard."""
    try:
        result = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True)
        private_key = result.stdout.strip()
        
        pub_result = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True,
            text=True,
            check=True,
        )
        public_key = pub_result.stdout.strip()
        
        return private_key, public_key
    except subprocess.CalledProcessError as exc:
        typer.secho(f"Erro ao gerar chaves: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1)


def _read_server_config() -> dict:
    """Lê configuração do servidor."""
    if not WG0_CONF.exists():
        typer.secho(
            f"Arquivo {WG0_CONF} não encontrado. Execute 'raijin vpn' primeiro.",
            fg=typer.colors.RED
        )
        raise typer.Exit(1)
    
    content = WG0_CONF.read_text()
    
    # Extrai informações do servidor
    server_public_key = ""
    server_port = ""
    server_address = ""
    endpoint = ""
    dns = ""
    
    for line in content.split("\n"):
        if "ListenPort" in line:
            server_port = line.split("=")[1].strip()
        elif "Address" in line and not server_address:
            server_address = line.split("=")[1].strip()
        elif "PrivateKey" in line:
            # Gera chave pública do servidor a partir da privada
            private_key = line.split("=")[1].strip()
            try:
                result = subprocess.run(
                    ["wg", "pubkey"],
                    input=private_key,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                server_public_key = result.stdout.strip()
            except:
                pass
    
    # Tenta encontrar endpoint nos peers existentes
    peer_match = re.search(r"# Endpoint: (.+)", content)
    if peer_match:
        endpoint = peer_match.group(1)
    
    # Tenta encontrar DNS
    dns_match = re.search(r"# DNS: (.+)", content)
    if dns_match:
        dns = dns_match.group(1)
    
    return {
        "public_key": server_public_key,
        "port": server_port,
        "address": server_address.split("/")[0] if server_address else "",
        "network": server_address,
        "endpoint": endpoint,
        "dns": dns or "1.1.1.1,8.8.8.8",
    }


def _list_existing_clients() -> List[dict]:
    """Lista clientes existentes."""
    if not WG0_CONF.exists():
        return []
    
    content = WG0_CONF.read_text()
    clients = []
    
    # Parse peers - suporta múltiplos formatos de comentário
    lines = content.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Detecta início de um bloco [Peer]
        if line == "[Peer]":
            peer_name = None
            public_key = None
            allowed_ips = None
            
            # Verifica linha anterior para comentário com nome
            if i > 0:
                prev_line = lines[i - 1].strip()
                # Formato: "# cliente_nome" ou "# Cliente: nome"
                if prev_line.startswith("#"):
                    comment = prev_line[1:].strip()
                    if comment.lower().startswith("cliente:"):
                        peer_name = comment.split(":", 1)[1].strip()
                    else:
                        # Nome direto após # (formato do módulo vpn)
                        peer_name = comment
            
            # Lê configurações do peer
            i += 1
            while i < len(lines):
                peer_line = lines[i].strip()
                if peer_line.startswith("[") or (peer_line.startswith("#") and i + 1 < len(lines) and lines[i + 1].strip() == "[Peer]"):
                    break
                
                if peer_line.startswith("PublicKey"):
                    public_key = peer_line.split("=", 1)[1].strip()
                elif peer_line.startswith("AllowedIPs"):
                    allowed_ips = peer_line.split("=", 1)[1].strip()
                # Comentário inline com nome do cliente
                elif peer_line.startswith("#") and not peer_name:
                    peer_name = peer_line[1:].strip()
                
                i += 1
            
            # Adiciona peer se tiver pelo menos chave pública
            if public_key:
                clients.append({
                    "name": peer_name or f"cliente_{len(clients) + 1}",
                    "public_key": public_key,
                    "ip": allowed_ips or "N/A",
                })
            continue
        
        i += 1
    
    return clients


def _get_next_client_ip(server_config: dict) -> str:
    """Calcula próximo IP disponível para cliente."""
    network = server_config["network"]
    base_ip = network.split("/")[0]
    base_parts = base_ip.rsplit(".", 1)
    base_network = base_parts[0]
    
    existing_clients = _list_existing_clients()
    used_ips = {client["ip"].split("/")[0] for client in existing_clients}
    used_ips.add(base_ip)  # IP do servidor
    
    # Procura próximo IP disponível
    for i in range(2, 255):
        candidate = f"{base_network}.{i}"
        if candidate not in used_ips:
            return f"{candidate}/32"
    
    typer.secho("Erro: Rede VPN cheia (254 clientes)", fg=typer.colors.RED)
    raise typer.Exit(1)


def _add_peer_to_server(name: str, public_key: str, client_ip: str, ctx: ExecutionContext) -> None:
    """Adiciona peer ao arquivo de configuração do servidor."""
    content = WG0_CONF.read_text()
    
    # Remove linhas em branco extras no final
    content = content.rstrip() + "\n"
    
    # Formato compatível com o módulo vpn original
    peer_block = f"""
# {name}
[Peer]
PublicKey = {public_key}
AllowedIPs = {client_ip}
"""
    
    # Adiciona peer ao final
    content += peer_block
    
    write_file(WG0_CONF, content, ctx)
    
    # Recarrega configuração via wg syncconf (mais rápido) ou restart
    typer.echo("Recarregando WireGuard...")
    # Tenta wg syncconf primeiro (não derruba conexões existentes)
    result = run_cmd(
        ["bash", "-c", f"wg syncconf wg0 <(wg-quick strip wg0)"],
        ctx,
        check=False
    )
    if result.returncode != 0:
        # Fallback para restart
        run_cmd(["systemctl", "restart", "wg-quick@wg0"], ctx, check=False)


def _remove_peer_from_server(public_key: str, ctx: ExecutionContext) -> None:
    """Remove peer do arquivo de configuração do servidor."""
    content = WG0_CONF.read_text()
    
    # Remove bloco do peer - suporta múltiplos formatos
    lines = content.split("\n")
    new_lines = []
    skip_until_next_section = False
    
    for i, line in enumerate(lines):
        if f"PublicKey = {public_key}" in line:
            skip_until_next_section = True
            # Remove também o comentário anterior e [Peer]
            while new_lines and (
                new_lines[-1].startswith("#") or 
                new_lines[-1].strip() == "" or
                new_lines[-1].strip() == "[Peer]"
            ):
                new_lines.pop()
            continue
        
        if skip_until_next_section:
            # Próximo peer ou seção
            stripped = line.strip()
            if stripped.startswith("[") or (stripped.startswith("#") and i + 1 < len(lines) and lines[i + 1].strip() == "[Peer]"):
                skip_until_next_section = False
            else:
                continue
        
        new_lines.append(line)
    
    # Remove linhas em branco extras no final
    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()
    
    write_file(WG0_CONF, "\n".join(new_lines) + "\n", ctx)
    
    # Recarrega configuração
    typer.echo("Recarregando WireGuard...")
    result = run_cmd(
        ["bash", "-c", f"wg syncconf wg0 <(wg-quick strip wg0)"],
        ctx,
        check=False
    )
    if result.returncode != 0:
        run_cmd(["systemctl", "restart", "wg-quick@wg0"], ctx, check=False)


def _create_client_config(
    name: str,
    private_key: str,
    public_key: str,
    client_ip: str,
    server_config: dict,
) -> str:
    """Cria arquivo de configuração do cliente."""
    server_ip = server_config["address"]
    server_network = server_config["network"]
    dns = server_config["dns"]
    endpoint = server_config["endpoint"]
    server_public_key = server_config["public_key"]
    server_port = server_config["port"]
    
    if not endpoint:
        endpoint = typer.prompt("Endpoint público do servidor (IP ou domínio)")
    
    # Inclui chave pública do cliente como comentário para referência rápida
    config = f"""# Cliente: {name}
# PublicKey: {public_key}
[Interface]
PrivateKey = {private_key}
Address = {client_ip}
DNS = {dns}

[Peer]
PublicKey = {server_public_key}
Endpoint = {endpoint}:{server_port}
AllowedIPs = {server_network}, 10.0.0.0/8
PersistentKeepalive = 25
"""
    
    return config


def add_client(ctx: ExecutionContext) -> None:
    """Adiciona novo cliente VPN."""
    require_root(ctx)
    
    typer.echo("Adicionando novo cliente WireGuard VPN...\n")
    
    # Lê configuração do servidor
    server_config = _read_server_config()
    
    # Lista clientes existentes
    existing_clients = _list_existing_clients()
    if existing_clients:
        typer.echo("Clientes existentes:")
        for client in existing_clients:
            typer.echo(f"  - {client['name']} ({client['ip']})")
        typer.echo("")
    
    # Solicita informações do novo cliente
    name = typer.prompt("Nome do cliente")
    
    # Verifica se já existe
    if any(c["name"] == name for c in existing_clients):
        typer.secho(f"Cliente '{name}' já existe!", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Gera chaves
    typer.echo("Gerando par de chaves...")
    private_key, public_key = _generate_keypair()
    
    # Calcula próximo IP
    client_ip = _get_next_client_ip(server_config)
    
    typer.echo(f"IP atribuído: {client_ip}")
    
    # Cria diretório de clientes
    CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Cria configuração do cliente
    client_config = _create_client_config(name, private_key, public_key, client_ip, server_config)
    
    client_file = CLIENTS_DIR / f"{name}.conf"
    write_file(client_file, client_config, ctx)
    client_file.chmod(0o600)
    
    # Salva chaves separadamente
    key_file = CLIENTS_DIR / f"{name}.key"
    write_file(key_file, f"Private: {private_key}\nPublic: {public_key}\n", ctx)
    key_file.chmod(0o600)
    
    # Adiciona peer ao servidor
    _add_peer_to_server(name, public_key, client_ip, ctx)
    
    typer.secho(f"\n✓ Cliente '{name}' adicionado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"\nArquivo de configuração: {client_file}")
    typer.echo("\nPara usar:")
    typer.echo(f"  1. Copie o arquivo: scp root@servidor:{client_file} .")
    typer.echo(f"  2. Importe no WireGuard (Windows/Mac/Linux)")
    typer.echo(f"  3. Ou gere QR code: qrencode -t ansiutf8 {client_file}")


def list_clients(ctx: ExecutionContext) -> None:
    """Lista todos os clientes VPN."""
    require_root(ctx)
    
    clients = _list_existing_clients()
    
    if not clients:
        typer.echo("Nenhum cliente configurado.")
        return
    
    typer.secho(f"\n{'Nome':<20} {'IP':<20} {'Chave Pública'}", fg=typer.colors.CYAN, bold=True)
    typer.echo("=" * 80)
    
    for client in clients:
        name = client.get("name", "Desconhecido")
        ip = client.get("ip", "N/A")
        pubkey = client.get("public_key", "N/A")[:40] + "..."
        typer.echo(f"{name:<20} {ip:<20} {pubkey}")
    
    typer.echo(f"\nTotal: {len(clients)} cliente(s)")


def remove_client(ctx: ExecutionContext) -> None:
    """Remove cliente VPN."""
    require_root(ctx)
    
    clients = _list_existing_clients()
    
    if not clients:
        typer.echo("Nenhum cliente configurado.")
        return
    
    # Mostra lista
    typer.echo("Clientes disponíveis:")
    for i, client in enumerate(clients, 1):
        typer.echo(f"  {i}. {client['name']} ({client['ip']})")
    
    # Solicita nome
    name = typer.prompt("\nNome do cliente para remover")
    
    # Encontra cliente
    client = next((c for c in clients if c["name"] == name), None)
    if not client:
        typer.secho(f"Cliente '{name}' não encontrado!", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Confirma remoção
    confirm = typer.confirm(
        f"Remover cliente '{name}' ({client['ip']})?",
        default=False
    )
    
    if not confirm:
        typer.echo("Operação cancelada.")
        return
    
    # Remove do servidor
    _remove_peer_from_server(client["public_key"], ctx)
    
    # Remove arquivos locais
    client_file = CLIENTS_DIR / f"{name}.conf"
    key_file = CLIENTS_DIR / f"{name}.key"
    
    if client_file.exists():
        client_file.unlink()
    if key_file.exists():
        key_file.unlink()
    
    typer.secho(f"\n✓ Cliente '{name}' removido com sucesso!", fg=typer.colors.GREEN, bold=True)


def show_client_config(ctx: ExecutionContext) -> None:
    """Mostra configuração de um cliente."""
    require_root(ctx)
    
    clients = _list_existing_clients()
    
    if not clients:
        typer.echo("Nenhum cliente configurado.")
        return
    
    # Lista clientes
    typer.echo("Clientes disponíveis:")
    for client in clients:
        typer.echo(f"  - {client['name']}")
    
    # Solicita nome
    name = typer.prompt("\nNome do cliente")
    
    client_file = CLIENTS_DIR / f"{name}.conf"
    
    if not client_file.exists():
        typer.secho(f"Arquivo de configuração não encontrado: {client_file}", fg=typer.colors.RED)
        typer.echo("\nDica: O cliente pode ter sido criado pelo módulo 'vpn' (inicial).")
        typer.echo(f"Verifique se existe: {CLIENTS_DIR}")
        raise typer.Exit(1)
    
    typer.echo(f"\n{'='*60}")
    typer.echo(f"Configuração do cliente: {name}")
    typer.echo(f"Arquivo: {client_file}")
    typer.echo(f"{'='*60}\n")
    
    typer.echo(client_file.read_text())
    
    # Detecta hostname/IP do servidor
    import socket
    hostname = socket.gethostname()
    
    typer.echo(f"\n{'='*60}")
    typer.secho("COMO COPIAR PARA WINDOWS/MAC/LINUX:", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"{'='*60}")
    
    typer.echo("\n📋 Opção 1 - SCP (requer SSH configurado):")
    typer.echo(f"   scp usuario@{hostname}:{client_file} .")
    typer.echo(f"   # ou com IP: scp usuario@SEU_IP:{client_file} .")
    
    typer.echo("\n📋 Opção 2 - Copiar conteúdo manualmente:")
    typer.echo("   1. Copie o texto acima (entre as linhas de '=')")
    typer.echo(f"   2. No Windows, crie arquivo: {name}.conf")
    typer.echo("   3. Cole o conteúdo e salve")
    
    typer.echo("\n📋 Opção 3 - SFTP (FileZilla, WinSCP):")
    typer.echo(f"   Conecte no servidor e baixe: {client_file}")
    
    typer.echo("\n📱 Para celular (QR Code):")
    typer.echo(f"   qrencode -t ansiutf8 < {client_file}")
    
    typer.echo(f"\n{'='*60}")
    typer.secho("NO WINDOWS 11:", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"{'='*60}")
    typer.echo("   1. Baixe WireGuard: https://www.wireguard.com/install/")
    typer.echo("   2. Abra WireGuard → 'Import tunnel(s) from file...'")
    typer.echo(f"   3. Selecione o arquivo {name}.conf")
    typer.echo("   4. Clique 'Activate' para conectar")
    typer.echo("")


def verify_config(ctx: ExecutionContext) -> None:
    """Verifica se a configuração do WireGuard está correta."""
    require_root(ctx)
    
    typer.secho("\n🔍 Verificação de Configuração WireGuard", fg=typer.colors.CYAN, bold=True)
    typer.echo("="*60)
    
    errors = []
    warnings = []
    
    # 1. Verificar se arquivo existe
    if not WG0_CONF.exists():
        typer.secho("✗ Arquivo wg0.conf não encontrado!", fg=typer.colors.RED)
        typer.echo("  Execute 'raijin vpn' primeiro para configurar o servidor.")
        return
    
    content = WG0_CONF.read_text()
    typer.secho("✓ Arquivo wg0.conf encontrado", fg=typer.colors.GREEN)
    
    # 2. Verificar [Interface]
    typer.echo("\n📋 Verificando [Interface]...")
    
    if "[Interface]" not in content:
        errors.append("Falta seção [Interface] no arquivo!")
    else:
        typer.secho("  ✓ Seção [Interface] presente", fg=typer.colors.GREEN)
    
    # 3. Verificar ListenPort
    port_match = re.search(r'^ListenPort\s*=\s*(\d+)', content, re.MULTILINE)
    if not port_match:
        errors.append("ListenPort não definida!")
    else:
        port = port_match.group(1)
        if port == "22":
            errors.append(f"ListenPort={port} está conflitando com SSH! Use 51820.")
        elif port != "51820":
            warnings.append(f"ListenPort={port} (padrão é 51820)")
        else:
            typer.secho(f"  ✓ ListenPort = {port}", fg=typer.colors.GREEN)
    
    # 4. Verificar PrivateKey e calcular PublicKey
    typer.echo("\n🔑 Verificando chaves...")
    
    priv_match = re.search(r'^PrivateKey\s*=\s*(\S+)', content, re.MULTILINE)
    if not priv_match:
        errors.append("PrivateKey do servidor não encontrada!")
    else:
        private_key = priv_match.group(1)
        try:
            result = subprocess.run(
                ["wg", "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                check=True,
            )
            server_public_key = result.stdout.strip()
            typer.secho(f"  ✓ Chave Pública do Servidor:", fg=typer.colors.GREEN)
            typer.secho(f"    {server_public_key}", fg=typer.colors.CYAN, bold=True)
            typer.echo("    ↑ USE ESTA CHAVE no [Peer].PublicKey dos CLIENTES!")
        except subprocess.CalledProcessError:
            errors.append("Erro ao calcular chave pública do servidor!")
    
    # 5. Verificar peers
    typer.echo("\n👥 Verificando peers...")
    
    peers = re.findall(r'\[Peer\].*?(?=\[|$)', content, re.DOTALL)
    if not peers:
        warnings.append("Nenhum peer (cliente) configurado!")
    else:
        typer.echo(f"  {len(peers)} peer(s) configurado(s)")
        
        for i, peer in enumerate(peers, 1):
            pub_match = re.search(r'PublicKey\s*=\s*(\S+)', peer)
            ip_match = re.search(r'AllowedIPs\s*=\s*(\S+)', peer)
            
            if pub_match:
                peer_pubkey = pub_match.group(1)
                # Verificar se a chave do peer é a mesma do servidor (erro comum!)
                if 'server_public_key' in dir() and peer_pubkey == server_public_key:
                    errors.append(f"Peer {i}: PublicKey é igual à do servidor! Erro de configuração.")
                else:
                    typer.secho(f"  ✓ Peer {i}: {peer_pubkey[:20]}...", fg=typer.colors.GREEN)
            
            if ip_match:
                peer_ip = ip_match.group(1)
                typer.echo(f"    AllowedIPs: {peer_ip}")
    
    # 6. Verificar PostUp/PostDown
    typer.echo("\n🔧 Verificando iptables rules...")
    
    if "MASQUERADE" not in content:
        errors.append("Regra MASQUERADE não encontrada no PostUp!")
    else:
        typer.secho("  ✓ Regra MASQUERADE presente", fg=typer.colors.GREEN)
    
    if "FORWARD" not in content:
        errors.append("Regras FORWARD não encontradas no PostUp!")
    else:
        typer.secho("  ✓ Regras FORWARD presentes", fg=typer.colors.GREEN)
    
    # 7. Verificar se WireGuard está rodando
    typer.echo("\n🚀 Verificando serviço...")
    
    result = subprocess.run(["systemctl", "is-active", "wg-quick@wg0"], capture_output=True, text=True)
    if result.stdout.strip() == "active":
        typer.secho("  ✓ WireGuard está rodando", fg=typer.colors.GREEN)
        
        # Verificar porta real sendo usada
        wg_result = subprocess.run(["wg", "show", "wg0", "listen-port"], capture_output=True, text=True)
        actual_port = wg_result.stdout.strip()
        if actual_port and port_match:
            if actual_port != port_match.group(1):
                errors.append(f"CRÍTICO: Porta configurada ({port_match.group(1)}) difere da porta real ({actual_port})!")
                errors.append("Reinicie o WireGuard: sudo systemctl restart wg-quick@wg0")
            else:
                typer.secho(f"  ✓ Escutando na porta {actual_port}", fg=typer.colors.GREEN)
    else:
        errors.append("WireGuard não está rodando!")
    
    # 8. Resumo
    typer.echo("\n" + "="*60)
    
    if errors:
        typer.secho("❌ ERROS ENCONTRADOS:", fg=typer.colors.RED, bold=True)
        for error in errors:
            typer.secho(f"  • {error}", fg=typer.colors.RED)
    
    if warnings:
        typer.secho("\n⚠️  AVISOS:", fg=typer.colors.YELLOW, bold=True)
        for warning in warnings:
            typer.secho(f"  • {warning}", fg=typer.colors.YELLOW)
    
    if not errors and not warnings:
        typer.secho("✅ Configuração do servidor OK!", fg=typer.colors.GREEN, bold=True)
    
    typer.echo("\n" + "="*60)
    typer.secho("CHECKLIST PARA CLIENTES:", fg=typer.colors.CYAN, bold=True)
    typer.echo("="*60)
    typer.echo("1. [Peer].PublicKey deve ser a chave pública do SERVIDOR (acima)")
    typer.echo("2. [Peer].Endpoint deve ser IP_PÚBLICO:PORTA (ex: 177.128.86.89:51820)")
    typer.echo("3. [Interface].PrivateKey deve ser a chave privada do CLIENTE (não do servidor!)")
    typer.echo("4. [Interface].Address deve ser único para cada cliente (ex: 10.8.0.2/32)")
    typer.echo("")


def diagnose_and_fix(ctx: ExecutionContext) -> None:
    """Diagnostica e corrige problemas de roteamento da VPN."""
    require_root(ctx)
    
    typer.secho("\n🔍 Diagnóstico de VPN", fg=typer.colors.CYAN, bold=True)
    typer.echo("="*60)
    
    # 1. Verificar se WireGuard está rodando
    typer.echo("\n1. Verificando status do WireGuard...")
    result = run_cmd(["systemctl", "is-active", "wg-quick@wg0"], ctx, check=False)
    
    if result.returncode != 0:
        typer.secho("   ✗ WireGuard não está rodando!", fg=typer.colors.RED)
        typer.echo("   Execute: systemctl start wg-quick@wg0")
        return
    
    typer.secho("   ✓ WireGuard ativo", fg=typer.colors.GREEN)
    
    # 2. Verificar IP forwarding
    typer.echo("\n2. Verificando IP forwarding...")
    try:
        forward = Path("/proc/sys/net/ipv4/ip_forward").read_text().strip()
        if forward == "1":
            typer.secho("   ✓ IP forwarding habilitado", fg=typer.colors.GREEN)
        else:
            typer.secho("   ✗ IP forwarding desabilitado", fg=typer.colors.YELLOW)
            typer.echo("   Habilitando...")
            run_cmd(["sysctl", "-w", "net.ipv4.ip_forward=1"], ctx)
            typer.secho("   ✓ IP forwarding habilitado", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"   ✗ Erro ao verificar: {e}", fg=typer.colors.RED)
    
    # 3. Detectar interface de rede principal
    typer.echo("\n3. Detectando interface de rede...")
    result = run_cmd(["ip", "route", "show", "default"], ctx, check=False)
    
    if result.returncode != 0:
        typer.secho("   ✗ Não foi possível detectar interface", fg=typer.colors.RED)
        return
    
    match = re.search(r'dev\s+(\S+)', result.stdout)
    if not match:
        typer.secho("   ✗ Interface não encontrada", fg=typer.colors.RED)
        return
    
    iface = match.group(1)
    typer.secho(f"   ✓ Interface detectada: {iface}", fg=typer.colors.GREEN)
    
    # 4. Verificar regra MASQUERADE
    typer.echo("\n4. Verificando regra MASQUERADE...")
    result = run_cmd(
        ["iptables", "-t", "nat", "-L", "POSTROUTING", "-v", "-n"],
        ctx,
        check=False
    )
    
    has_masquerade = False
    if "10.8.0.0/24" in result.stdout and "MASQUERADE" in result.stdout:
        has_masquerade = True
        typer.secho("   ✓ Regra MASQUERADE existente", fg=typer.colors.GREEN)
    else:
        typer.secho("   ✗ Regra MASQUERADE não encontrada", fg=typer.colors.YELLOW)
        typer.echo(f"   Adicionando regra para interface {iface}...")
        
        run_cmd([
            "iptables", "-t", "nat", "-A", "POSTROUTING",
            "-s", "10.8.0.0/24", "-o", iface, "-j", "MASQUERADE"
        ], ctx)
        
        typer.secho("   ✓ Regra MASQUERADE adicionada", fg=typer.colors.GREEN)
    
    # 5. Verificar UFW routed
    typer.echo("\n5. Verificando UFW routed...")
    result = run_cmd(["ufw", "status", "verbose"], ctx, check=False)
    
    if "deny (routed)" in result.stdout.lower():
        typer.secho("   ✗ UFW está bloqueando routed", fg=typer.colors.YELLOW)
        typer.echo("   Configurando UFW para permitir routed...")
        
        run_cmd(["ufw", "default", "allow", "routed"], ctx, check=False)
        typer.secho("   ✓ UFW configurado", fg=typer.colors.GREEN)
    else:
        typer.secho("   ✓ UFW permite routed", fg=typer.colors.GREEN)
    
    # 6. Verificar regras de FORWARD para wg0
    typer.echo("\n6. Verificando regras FORWARD...")
    result = run_cmd(["iptables", "-L", "FORWARD", "-v", "-n"], ctx, check=False)
    
    has_forward_in = "wg0" in result.stdout and "ACCEPT" in result.stdout
    
    if not has_forward_in:
        typer.secho("   ✗ Regras FORWARD ausentes", fg=typer.colors.YELLOW)
        typer.echo("   Adicionando regras FORWARD...")
        
        run_cmd(["iptables", "-A", "FORWARD", "-i", "wg0", "-j", "ACCEPT"], ctx, check=False)
        run_cmd(["iptables", "-A", "FORWARD", "-o", "wg0", "-j", "ACCEPT"], ctx, check=False)
        
        typer.secho("   ✓ Regras FORWARD adicionadas", fg=typer.colors.GREEN)
    else:
        typer.secho("   ✓ Regras FORWARD existentes", fg=typer.colors.GREEN)
    
    # 7. Verificar UFW permite wg0
    typer.echo("\n7. Verificando UFW para wg0...")
    result = run_cmd(["ufw", "status"], ctx, check=False)
    
    if "wg0" not in result.stdout:
        typer.secho("   ✗ UFW não permite wg0", fg=typer.colors.YELLOW)
        typer.echo("   Adicionando regra UFW...")
        
        run_cmd(["ufw", "allow", "in", "on", "wg0"], ctx, check=False)
        typer.secho("   ✓ UFW configurado para wg0", fg=typer.colors.GREEN)
    else:
        typer.secho("   ✓ UFW permite wg0", fg=typer.colors.GREEN)
    
    # 8. Reiniciar WireGuard para aplicar mudanças
    typer.echo("\n8. Reiniciando WireGuard...")
    run_cmd(["systemctl", "restart", "wg-quick@wg0"], ctx)
    typer.secho("   ✓ WireGuard reiniciado", fg=typer.colors.GREEN)
    
    # 9. Verificar peers conectados
    typer.echo("\n9. Verificando peers conectados...")
    result = run_cmd(["wg", "show"], ctx, check=False)
    
    peer_count = result.stdout.count("peer:")
    typer.echo(f"   Peers configurados: {peer_count}")
    
    if "latest handshake" in result.stdout.lower():
        typer.secho("   ✓ Handshake detectado (cliente conectado)", fg=typer.colors.GREEN)
    else:
        typer.secho("   ⚠ Nenhum handshake recente", fg=typer.colors.YELLOW)
        typer.echo("   Peça ao cliente para reconectar no WireGuard")
    
    # 10. Teste básico de conectividade
    typer.echo("\n10. Testando conectividade VPN...")
    result = run_cmd(["ping", "-c", "2", "-W", "1", "10.8.0.1"], ctx, check=False)
    
    if result.returncode == 0:
        typer.secho("   ✓ Ping para 10.8.0.1 bem-sucedido", fg=typer.colors.GREEN)
    else:
        typer.secho("   ⚠ Ping falhou (normal se nenhum cliente conectado)", fg=typer.colors.YELLOW)
    
    typer.echo("\n" + "="*60)
    typer.secho("✓ Diagnóstico concluído!", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nPróximos passos:")
    typer.echo("  1. No cliente Windows, desconecte e reconecte o túnel WireGuard")
    typer.echo("  2. Teste: ping 10.8.0.1")
    typer.echo("  3. Verifique 'sudo wg show' para ver handshake")
    typer.echo("")


def run(ctx: ExecutionContext) -> None:
    """Menu interativo para gerenciar clientes VPN."""
    require_root(ctx)
    
    while True:
        typer.echo("\n" + "="*60)
        typer.secho("Gerenciamento de Clientes VPN", fg=typer.colors.CYAN, bold=True)
        typer.echo("="*60)
        typer.echo("\n1. Adicionar cliente")
        typer.echo("2. Listar clientes")
        typer.echo("3. Remover cliente")
        typer.echo("4. Mostrar configuração de cliente")
        typer.echo("5. Verificar configuração do servidor")
        typer.echo("6. Diagnosticar e corrigir roteamento")
        typer.echo("7. Sair")
        
        choice = typer.prompt("\nEscolha uma opção", default="7")
        
        try:
            if choice == "1":
                add_client(ctx)
            elif choice == "2":
                list_clients(ctx)
            elif choice == "3":
                remove_client(ctx)
            elif choice == "4":
                show_client_config(ctx)
            elif choice == "5":
                verify_config(ctx)
            elif choice == "6":
                diagnose_and_fix(ctx)
            elif choice == "7":
                typer.echo("Saindo...")
                break
            else:
                typer.secho("Opção inválida!", fg=typer.colors.RED)
        except (KeyboardInterrupt, typer.Exit):
            typer.echo("\n")
            continue
