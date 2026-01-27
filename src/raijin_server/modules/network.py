"""Configuracao de rede (IP fixo) via Netplan."""

import os
from pathlib import Path

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


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Configurando IP fixo (Netplan)...")

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
