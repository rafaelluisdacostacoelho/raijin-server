"""Gerenciamento de configuração de rede via environment variables.

Este módulo permite reconfigurar IP, Gateway, DNS de forma segura
usando variáveis de ambiente em vez de valores hardcoded.

Variáveis suportadas:
    RAIJIN_NET_INTERFACE: Interface de rede (ex: eth0, ens18)
    RAIJIN_NET_IP: IP com CIDR (ex: 192.168.1.100/24)
    RAIJIN_NET_GATEWAY: Gateway padrão (ex: 192.168.1.1)
    RAIJIN_NET_DNS: DNS servers separados por vírgula
    RAIJIN_NET_MTU: MTU da interface (padrão: 1500)
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import typer

from raijin_server.utils import ExecutionContext, require_root, run_cmd, write_file


def _get_env(key: str, default: str = "") -> str:
    """Obtém variável de ambiente com fallback."""
    return os.environ.get(key, default).strip()


def _validate_ip_cidr(ip_cidr: str) -> bool:
    """Valida formato IP/CIDR (ex: 192.168.1.100/24)."""
    pattern = r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$"
    if not re.match(pattern, ip_cidr):
        return False
    ip, cidr = ip_cidr.split("/")
    octets = ip.split(".")
    if not all(0 <= int(o) <= 255 for o in octets):
        return False
    if not 1 <= int(cidr) <= 32:
        return False
    return True


def _validate_ip(ip: str) -> bool:
    """Valida formato IP simples."""
    pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if not re.match(pattern, ip):
        return False
    octets = ip.split(".")
    return all(0 <= int(o) <= 255 for o in octets)


def _get_current_config() -> dict:
    """Obtém configuração atual de rede."""
    config = {
        "interface": "",
        "ip": "",
        "gateway": "",
        "dns": [],
    }
    
    try:
        # Detectar interface principal
        result = subprocess.run(
            ["ip", "-4", "route", "show", "default"],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout:
            parts = result.stdout.split()
            if "dev" in parts:
                idx = parts.index("dev")
                config["interface"] = parts[idx + 1]
            if "via" in parts:
                idx = parts.index("via")
                config["gateway"] = parts[idx + 1]
        
        # Detectar IP atual
        if config["interface"]:
            result = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", config["interface"]],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                parts = result.stdout.split()
                for i, p in enumerate(parts):
                    if "/" in p and _validate_ip_cidr(p):
                        config["ip"] = p
                        break
        
        # Detectar DNS
        resolv = Path("/etc/resolv.conf")
        if resolv.exists():
            for line in resolv.read_text().splitlines():
                if line.strip().startswith("nameserver"):
                    dns = line.split()[1]
                    if _validate_ip(dns):
                        config["dns"].append(dns)
    except Exception:
        pass
    
    return config


def _detect_interfaces() -> list:
    """Lista interfaces de rede disponíveis."""
    interfaces = []
    try:
        result = subprocess.run(
            ["ip", "-o", "link", "show"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                iface = parts[1].strip()
                # Ignorar interfaces virtuais
                if not any(iface.startswith(p) for p in ("lo", "docker", "veth", "br-", "cni", "flannel", "cali")):
                    interfaces.append(iface)
    except Exception:
        pass
    return interfaces


def _generate_netplan(interface: str, ip: str, gateway: str, dns_list: list, mtu: int = 1500) -> str:
    """Gera configuração Netplan."""
    dns_str = ", ".join(dns_list)
    return f"""# Gerado pelo Raijin Server - Network Config
# Data: {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}
network:
  version: 2
  renderer: networkd
  ethernets:
    {interface}:
      dhcp4: false
      addresses:
        - {ip}
      routes:
        - to: default
          via: {gateway}
      nameservers:
        addresses: [{dns_str}]
      mtu: {mtu}
"""


def show_config(ctx: ExecutionContext) -> None:
    """Mostra configuração atual de rede."""
    current = _get_current_config()
    
    typer.secho("\n📡 Configuração Atual de Rede", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Interface: {current['interface'] or 'N/A'}")
    typer.echo(f"  IP:        {current['ip'] or 'N/A'}")
    typer.echo(f"  Gateway:   {current['gateway'] or 'N/A'}")
    typer.echo(f"  DNS:       {', '.join(current['dns']) or 'N/A'}")
    
    typer.secho("\n🔧 Variáveis de Ambiente Configuradas", fg=typer.colors.CYAN, bold=True)
    env_vars = [
        ("RAIJIN_NET_INTERFACE", _get_env("RAIJIN_NET_INTERFACE")),
        ("RAIJIN_NET_IP", _get_env("RAIJIN_NET_IP")),
        ("RAIJIN_NET_GATEWAY", _get_env("RAIJIN_NET_GATEWAY")),
        ("RAIJIN_NET_DNS", _get_env("RAIJIN_NET_DNS")),
        ("RAIJIN_NET_MTU", _get_env("RAIJIN_NET_MTU", "1500")),
    ]
    
    for var, val in env_vars:
        status = "✓" if val else "✗"
        color = typer.colors.GREEN if val else typer.colors.YELLOW
        typer.secho(f"  {status} {var}={val or '(não definido)'}", fg=color)


def apply_config(ctx: ExecutionContext, force: bool = False) -> None:
    """Aplica configuração de rede baseada em environment variables."""
    require_root(ctx)
    
    # Obter configurações das envs
    interface = _get_env("RAIJIN_NET_INTERFACE")
    ip = _get_env("RAIJIN_NET_IP")
    gateway = _get_env("RAIJIN_NET_GATEWAY")
    dns_raw = _get_env("RAIJIN_NET_DNS")
    mtu = int(_get_env("RAIJIN_NET_MTU", "1500"))
    
    # Validar
    errors = []
    
    if not interface:
        available = _detect_interfaces()
        if available:
            typer.echo(f"Interfaces disponíveis: {', '.join(available)}")
        errors.append("RAIJIN_NET_INTERFACE não definido")
    
    if not ip:
        errors.append("RAIJIN_NET_IP não definido")
    elif not _validate_ip_cidr(ip):
        errors.append(f"RAIJIN_NET_IP inválido: {ip} (esperado: x.x.x.x/xx)")
    
    if not gateway:
        errors.append("RAIJIN_NET_GATEWAY não definido")
    elif not _validate_ip(gateway):
        errors.append(f"RAIJIN_NET_GATEWAY inválido: {gateway}")
    
    if not dns_raw:
        errors.append("RAIJIN_NET_DNS não definido")
    
    dns_list = [d.strip() for d in dns_raw.split(",") if d.strip()]
    for dns in dns_list:
        if not _validate_ip(dns):
            errors.append(f"DNS inválido: {dns}")
    
    if errors:
        typer.secho("\n❌ Erros de validação:", fg=typer.colors.RED)
        for e in errors:
            typer.echo(f"   • {e}")
        typer.echo("\nDefina as variáveis de ambiente antes de aplicar.")
        typer.echo("Exemplo:")
        typer.secho("  export RAIJIN_NET_INTERFACE=eth0", fg=typer.colors.CYAN)
        typer.secho("  export RAIJIN_NET_IP=192.168.1.100/24", fg=typer.colors.CYAN)
        typer.secho("  export RAIJIN_NET_GATEWAY=192.168.1.1", fg=typer.colors.CYAN)
        typer.secho("  export RAIJIN_NET_DNS=1.1.1.1,8.8.8.8", fg=typer.colors.CYAN)
        raise typer.Exit(code=1)
    
    # Mostrar preview
    typer.secho("\n📋 Configuração a ser aplicada:", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Interface: {interface}")
    typer.echo(f"  IP:        {ip}")
    typer.echo(f"  Gateway:   {gateway}")
    typer.echo(f"  DNS:       {', '.join(dns_list)}")
    typer.echo(f"  MTU:       {mtu}")
    
    if not force:
        typer.secho("\n⚠️  ATENÇÃO: Isso irá alterar sua configuração de rede!", fg=typer.colors.YELLOW)
        typer.echo("Se você estiver conectado remotamente, pode perder a conexão.")
        if not typer.confirm("Deseja continuar?", default=False):
            typer.echo("Operação cancelada.")
            return
    
    # Backup da configuração atual
    netplan_dir = Path("/etc/netplan")
    backup_dir = Path("/etc/netplan/backup")
    
    if not ctx.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for f in netplan_dir.glob("*.yaml"):
            if f.name != "backup":
                backup_path = backup_dir / f"{f.name}.bak"
                typer.echo(f"Backup: {f} -> {backup_path}")
                f.rename(backup_path)
    
    # Gerar e aplicar nova configuração
    netplan_content = _generate_netplan(interface, ip, gateway, dns_list, mtu)
    netplan_file = netplan_dir / "01-raijin-network.yaml"
    
    typer.echo(f"\nGerando {netplan_file}...")
    write_file(netplan_file, netplan_content, ctx)
    
    # Aplicar
    typer.echo("Aplicando configuração...")
    run_cmd(["netplan", "apply"], ctx)
    
    typer.secho("\n✓ Configuração de rede aplicada!", fg=typer.colors.GREEN)
    typer.echo("\nPara reverter, restaure os backups:")
    typer.secho(f"  sudo cp {backup_dir}/*.bak {netplan_dir}/", fg=typer.colors.CYAN)
    typer.secho("  sudo netplan apply", fg=typer.colors.CYAN)


def restore_backup(ctx: ExecutionContext) -> None:
    """Restaura backup da configuração de rede."""
    require_root(ctx)
    
    backup_dir = Path("/etc/netplan/backup")
    netplan_dir = Path("/etc/netplan")
    
    if not backup_dir.exists():
        typer.secho("Nenhum backup encontrado.", fg=typer.colors.YELLOW)
        return
    
    backups = list(backup_dir.glob("*.bak"))
    if not backups:
        typer.secho("Nenhum arquivo de backup encontrado.", fg=typer.colors.YELLOW)
        return
    
    typer.secho("Backups disponíveis:", fg=typer.colors.CYAN)
    for b in backups:
        typer.echo(f"  • {b.name}")
    
    if not typer.confirm("Restaurar backup?", default=True):
        return
    
    # Remove configuração atual do Raijin
    raijin_config = netplan_dir / "01-raijin-network.yaml"
    if raijin_config.exists() and not ctx.dry_run:
        raijin_config.unlink()
    
    # Restaura backups
    for b in backups:
        original_name = b.name.replace(".bak", "")
        dest = netplan_dir / original_name
        typer.echo(f"Restaurando {b} -> {dest}")
        if not ctx.dry_run:
            import shutil
            shutil.copy(b, dest)
    
    run_cmd(["netplan", "apply"], ctx)
    typer.secho("✓ Backup restaurado!", fg=typer.colors.GREEN)


def run(ctx: ExecutionContext, action: str = "show") -> None:
    """Gerencia configuração de rede.
    
    Args:
        action: show|apply|restore
    """
    if action == "show":
        show_config(ctx)
    elif action == "apply":
        apply_config(ctx)
    elif action == "restore":
        restore_backup(ctx)
    else:
        typer.secho(f"Ação desconhecida: {action}", fg=typer.colors.RED)
        typer.echo("Ações válidas: show, apply, restore")
