"""Configuracao de rede (IP fixo) via Netplan.

Este modulo eh OPCIONAL quando:
- IP fixo ja foi configurado no provedor ISP (ex: Ibi Internet Empresarial)
- IP estatico foi definido manualmente durante instalacao do SO
- Netplan ja possui configuracao funcional

Set RAIJIN_SKIP_NETWORK=1 para pular automaticamente em automacoes.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

from raijin_server.utils import ExecutionContext, require_root, run_cmd, write_file


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        data = Path("/proc/version").read_text().lower()
        return "microsoft" in data or "wsl" in data
    except OSError:
        return False


def _get_current_ip() -> Optional[str]:
    """Retorna o IP principal atual do sistema (excluindo loopback e docker)."""
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                iface = parts[1]
                # Ignora interfaces virtuais (docker, veth, br-, virbr, etc.)
                if any(iface.startswith(p) for p in ("docker", "veth", "br-", "virbr", "cni", "flannel")):
                    continue
                ip_cidr = parts[3]
                return ip_cidr
    except Exception:
        pass
    return None


def _has_static_netplan() -> bool:
    """Verifica se ja existe configuracao Netplan com IP estatico."""
    netplan_dir = Path("/etc/netplan")
    if not netplan_dir.exists():
        return False
    for f in netplan_dir.glob("*.yaml"):
        try:
            content = f.read_text()
            if "dhcp4: false" in content or "dhcp4: no" in content:
                return True
        except OSError:
            continue
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)

    # Permite pular via variavel de ambiente (para automacao)
    if os.environ.get("RAIJIN_SKIP_NETWORK", "").strip() in ("1", "true", "yes"):
        typer.secho(
            "RAIJIN_SKIP_NETWORK=1 detectado. Pulando configuracao de rede.",
            fg=typer.colors.YELLOW,
        )
        return

    current_ip = _get_current_ip()
    has_static = _has_static_netplan()

    # Se ja tem IP estatico configurado, oferece pular
    if current_ip and has_static:
        typer.secho(
            f"\n✓ IP estatico detectado: {current_ip}",
            fg=typer.colors.GREEN,
        )
        typer.secho(
            "  Parece que a rede ja esta configurada (Netplan com dhcp4: false).",
            fg=typer.colors.GREEN,
        )
        typer.echo("")
        if not typer.confirm(
            "Deseja reconfigurar a rede mesmo assim? (NAO recomendado se ja funciona)",
            default=False,
        ):
            typer.secho("Pulando configuracao de rede.", fg=typer.colors.CYAN)
            return
    elif current_ip:
        typer.secho(
            f"\n✓ IP atual: {current_ip}",
            fg=typer.colors.GREEN,
        )
        typer.echo(
            "  Se este IP foi configurado pelo seu provedor ISP ou durante a instalacao,\n"
            "  voce pode pular este passo."
        )
        typer.echo("")
        if not typer.confirm(
            "Deseja configurar IP estatico via Netplan?",
            default=True,
        ):
            typer.secho("Pulando configuracao de rede.", fg=typer.colors.CYAN)
            return

    typer.echo("\nConfigurando IP fixo (Netplan)...")

    wsl = _is_wsl()
    if wsl:
        typer.secho(
            "Ambiente WSL detectado: netplan pode nao ter efeito ou quebrar rede. Use apenas para gerar arquivo.",
            fg=typer.colors.YELLOW,
        )

    iface = typer.prompt("Interface", default="ens18")
    address = typer.prompt("Endereco CIDR", default="192.168.0.10/24")
    gateway = typer.prompt("Gateway", default="192.168.0.1")
    dns = typer.prompt("DNS (separe por virgula)", default="1.1.1.1,8.8.8.8")

    dns_list = ",".join([item.strip() for item in dns.split(",") if item.strip()])
    netplan_content = f"""network:
  version: 2
  renderer: networkd
  ethernets:
    {iface}:
      dhcp4: false
      addresses: [{address}]
      gateway4: {gateway}
      nameservers:
        addresses: [{dns_list}]
"""

    target = Path("/etc/netplan/01-raijin-static.yaml")
    write_file(target, netplan_content, ctx)

    apply_now = typer.confirm("Aplicar netplan agora?", default=not wsl)
    if apply_now:
        run_cmd(["netplan", "apply"], ctx)
    else:
        typer.echo("Netplan nao aplicado (apenas arquivo gerado).")
