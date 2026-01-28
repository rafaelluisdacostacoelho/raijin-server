"""Configuracao de servidor WireGuard e cliente inicial."""

from __future__ import annotations

import ipaddress
import os
import platform
import subprocess
import textwrap
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    apt_install,
    logger,
    require_root,
    run_cmd,
    write_file,
)

WIREGUARD_DIR = Path("/etc/wireguard")
CLIENTS_DIR = WIREGUARD_DIR / "clients"
SYSCTL_FILE = Path("/etc/sysctl.d/99-wireguard.conf")


def _is_secure_boot_enabled() -> bool:
    """Retorna True se Secure Boot estiver ativo (EFI)."""

    try:
        sb_path = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
        if not sb_path.exists():
            return False
        data = sb_path.read_bytes()
        # Estrutura: atributos (4 bytes) + valor (1 byte)
        return len(data) >= 5 and data[4] == 1
    except Exception:
        return False


def _kernel_headers_present() -> bool:
    """Verifica se os headers do kernel atual estao instalados."""

    release = platform.uname().release
    return Path(f"/lib/modules/{release}/build").exists()


def _modprobe_check(module: str) -> bool:
    """Tenta carregar o modulo em modo dry-run para validar disponibilidade."""

    try:
        result = subprocess.run(["modprobe", "-n", module], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _generate_keypair(
    label: str,
    private_path: Path,
    public_path: Path,
    ctx: ExecutionContext,
) -> tuple[str, str]:
    """Gera (ou reutiliza) chaves WireGuard, respeitando dry-run."""

    if ctx.dry_run:
        typer.echo(f"[dry-run] Geraria chaves WireGuard para {label}")
        return ("DRY_RUN_PRIVATE_KEY", "DRY_RUN_PUBLIC_KEY")

    if private_path.exists() and public_path.exists():
        return (private_path.read_text().strip(), public_path.read_text().strip())

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
    except subprocess.CalledProcessError as exc:
        msg = f"Falha ao gerar chaves WireGuard ({label}): {exc.stderr or exc}"
        ctx.errors.append(msg)
        raise typer.Exit(code=1) from exc

    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(private_key + "\n")
    public_path.write_text(public_key + "\n")
    os.chmod(private_path, 0o600)
    os.chmod(public_path, 0o600)
    logger.info("Chaves WireGuard gravadas em %s e %s", private_path, public_path)

    return private_key, public_key


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Configurando WireGuard (VPN site-to-site)...")

    if _is_secure_boot_enabled():
        typer.secho(
            "Secure Boot detectado: modulos DKMS (wireguard) podem exigir assinatura.\n"
            "Se o modulo nao carregar, assine-o ou desabilite Secure Boot temporariamente.",
            fg=typer.colors.YELLOW,
        )

    # NIC offload pode interferir em VPN/perf em alguns hardwares; aviso leve
    typer.secho(
        "Considere desabilitar offloads problemáticos em NICs (tso/gso/gro) se notar latência ou perda.",
        fg=typer.colors.YELLOW,
    )

    if not _kernel_headers_present():
        typer.secho(
            "Headers do kernel nao encontrados; instalando linux-headers-$(uname -r) para suportar WireGuard.",
            fg=typer.colors.YELLOW,
        )
        release = platform.uname().release
        header_pkg = f"linux-headers-{release}"
        apt_install([header_pkg], ctx)
        if not _kernel_headers_present():
            typer.secho(
                f"Headers ainda ausentes apos tentar instalar {header_pkg}. Verifique repos ou kernel custom.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    if not _modprobe_check("wireguard"):
        typer.secho(
            "Aviso: modulo wireguard pode nao estar disponivel (modprobe -n wireguard falhou).",
            fg=typer.colors.YELLOW,
        )

    apt_install(["wireguard", "wireguard-tools", "qrencode"], ctx)

    interface = typer.prompt("Interface WireGuard", default="wg0")
    vpn_cidr = typer.prompt("Rede VPN (CIDR)", default="10.8.0.0/24")
    network = ipaddress.ip_network(vpn_cidr)
    hosts = list(network.hosts())
    default_server_ip = str(hosts[0]) if hosts else str(network.network_address + 1)
    default_client_ip = str(hosts[1]) if len(hosts) > 1 else str(network.network_address + 2)

    server_ip = typer.prompt("IP do servidor na VPN", default=default_server_ip)
    server_address = f"{server_ip}/{network.prefixlen}"
    client_name = typer.prompt("Nome do cliente inicial", default="admin")
    client_ip = typer.prompt("IP do cliente inicial", default=default_client_ip)
    client_address = typer.prompt("Endereco/CIDR do cliente", default=f"{client_ip}/32")

    listen_port = typer.prompt("Porta WireGuard", default="51820")
    public_endpoint = typer.prompt("IP/Dominio publico de acesso", default="vpn.example.com")
    egress_iface = typer.prompt("Interface de saida (para NAT)", default="eth0")
    dns_servers = typer.prompt("DNS entregues aos clientes", default="1.1.1.1,8.8.8.8")
    keepalive = typer.prompt("PersistentKeepalive (segundos)", default="25")

    server_private_path = WIREGUARD_DIR / f"{interface}.key"
    server_public_path = WIREGUARD_DIR / f"{interface}.pub"
    client_private_path = CLIENTS_DIR / f"{client_name}.key"
    client_public_path = CLIENTS_DIR / f"{client_name}.pub"

    server_private, server_public = _generate_keypair("servidor", server_private_path, server_public_path, ctx)
    client_private, client_public = _generate_keypair("cliente", client_private_path, client_public_path, ctx)

    server_conf_path = WIREGUARD_DIR / f"{interface}.conf"
    client_conf_path = CLIENTS_DIR / f"{client_name}.conf"

    server_config = textwrap.dedent(
        f"""
        [Interface]
        Address = {server_address}
        ListenPort = {listen_port}
        PrivateKey = {server_private}
        SaveConfig = true
        PostUp = iptables -A FORWARD -i {interface} -j ACCEPT; iptables -A FORWARD -o {interface} -j ACCEPT; iptables -t nat -A POSTROUTING -o {egress_iface} -j MASQUERADE
        PostDown = iptables -D FORWARD -i {interface} -j ACCEPT; iptables -D FORWARD -o {interface} -j ACCEPT; iptables -t nat -D POSTROUTING -o {egress_iface} -j MASQUERADE

        [Peer]
        # {client_name}
        PublicKey = {client_public}
        AllowedIPs = {client_address}
        """
    ).strip() + "\n"

    client_config = textwrap.dedent(
        f"""
        [Interface]
        PrivateKey = {client_private}
        Address = {client_address}
        DNS = {dns_servers}

        [Peer]
        PublicKey = {server_public}
        AllowedIPs = {network.with_prefixlen}
        Endpoint = {public_endpoint}:{listen_port}
        PersistentKeepalive = {keepalive}
        """
    ).strip() + "\n"

    sysctl_content = "net.ipv4.ip_forward=1\nnet.ipv6.conf.all.forwarding=1\n"

    write_file(server_conf_path, server_config, ctx, mode=0o600)
    write_file(client_conf_path, client_config, ctx, mode=0o600)
    write_file(SYSCTL_FILE, sysctl_content, ctx)

    run_cmd(["sysctl", "-p", str(SYSCTL_FILE)], ctx)
    run_cmd(["ufw", "allow", f"{listen_port}/udp"], ctx, check=False)
    run_cmd(["systemctl", "enable", "--now", f"wg-quick@{interface}"], ctx)

    typer.secho("\n✓ WireGuard configurado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Configuracao do servidor: {server_conf_path}")
    typer.echo(f"Cliente inicial salvo em: {client_conf_path}")
    typer.echo("Para gerar QR code no terminal: qrencode -t ansiutf8 < caminho-do-cliente.conf")
    typer.echo("Para novos clientes, gere chaves com 'wg genkey' e adicione entradas em ambos os arquivos.")
    typer.echo("Clientes Linux/macOS: sudo wg-quick up ./cliente.conf | Windows: importe o arquivo no app WireGuard.")