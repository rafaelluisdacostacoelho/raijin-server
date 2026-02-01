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
    
    # Parse peers
    current_peer = {}
    for line in content.split("\n"):
        line = line.strip()
        
        if line.startswith("# Cliente:"):
            if current_peer:
                clients.append(current_peer)
            current_peer = {"name": line.split(":", 1)[1].strip()}
        elif line.startswith("PublicKey =") and current_peer:
            current_peer["public_key"] = line.split("=")[1].strip()
        elif line.startswith("AllowedIPs =") and current_peer:
            current_peer["ip"] = line.split("=")[1].strip()
    
    if current_peer:
        clients.append(current_peer)
    
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
    
    peer_block = f"""
# Cliente: {name}
[Peer]
PublicKey = {public_key}
AllowedIPs = {client_ip}
"""
    
    # Adiciona peer ao final
    content += "\n" + peer_block
    
    write_file(WG0_CONF, content, ctx)
    
    # Recarrega configuração
    typer.echo("Recarregando WireGuard...")
    run_cmd(["systemctl", "restart", "wg-quick@wg0"], ctx, check=False)


def _remove_peer_from_server(public_key: str, ctx: ExecutionContext) -> None:
    """Remove peer do arquivo de configuração do servidor."""
    content = WG0_CONF.read_text()
    
    # Remove bloco do peer
    lines = content.split("\n")
    new_lines = []
    skip_until_next_section = False
    
    for line in lines:
        if f"PublicKey = {public_key}" in line:
            skip_until_next_section = True
            # Remove também o comentário anterior
            if new_lines and new_lines[-1].startswith("# Cliente:"):
                new_lines.pop()
            if new_lines and new_lines[-1].strip() == "":
                new_lines.pop()
            if new_lines and new_lines[-1].strip() == "[Peer]":
                new_lines.pop()
            continue
        
        if skip_until_next_section:
            if line.startswith("[") or line.startswith("# Cliente:"):
                skip_until_next_section = False
            else:
                continue
        
        new_lines.append(line)
    
    write_file(WG0_CONF, "\n".join(new_lines), ctx)
    
    # Recarrega configuração
    typer.echo("Recarregando WireGuard...")
    run_cmd(["systemctl", "restart", "wg-quick@wg0"], ctx, check=False)


def _create_client_config(
    name: str,
    private_key: str,
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
    
    config = f"""[Interface]
# Cliente: {name}
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
    client_config = _create_client_config(name, private_key, client_ip, server_config)
    
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
        raise typer.Exit(1)
    
    typer.echo(f"\n{'='*60}")
    typer.echo(f"Configuração do cliente: {name}")
    typer.echo(f"Arquivo: {client_file}")
    typer.echo(f"{'='*60}\n")
    
    typer.echo(client_file.read_text())
    
    typer.echo(f"\n{'='*60}")
    typer.echo("\nPara copiar:")
    typer.echo(f"  scp root@servidor:{client_file} .")
    typer.echo("\nPara QR code (mobile):")
    typer.echo(f"  qrencode -t ansiutf8 {client_file}")


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
        typer.echo("5. Sair")
        
        choice = typer.prompt("\nEscolha uma opção", default="5")
        
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
                typer.echo("Saindo...")
                break
            else:
                typer.secho("Opção inválida!", fg=typer.colors.RED)
        except (KeyboardInterrupt, typer.Exit):
            typer.echo("\n")
            continue
