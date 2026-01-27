"""Tarefas de hardening do sistema."""

import subprocess

import typer

from raijin_server.utils import ExecutionContext, apt_install, apt_update, enable_service, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Aplicando hardening basico...")

    apt_update(ctx)
    apt_install(["fail2ban", "unattended-upgrades", "auditd"], ctx)

    enable_service("fail2ban", ctx)
    # Tenta iniciar auditd mas nao falha o fluxo se o kernel estiver sem auditing.
    run_cmd(["systemctl", "enable", "--now", "auditd"], ctx, check=False)
    if not ctx.dry_run:
        status = subprocess.run(
            ["systemctl", "is-active", "auditd"],
            capture_output=True,
            text=True,
        )
        if status.returncode != 0 or status.stdout.strip() != "active":
            typer.secho(
                "auditd nao ficou ativo. Verifique se o kernel esta com auditing habilitado (audit=1 no boot).",
                fg=typer.colors.YELLOW,
            )
    run_cmd(
        ["dpkg-reconfigure", "--priority=low", "unattended-upgrades"],
        ctx,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )

    # Reforca parametros de rede em tempo de execucao. Ajuste conforme necessidade.
    sysctls = [
        "net.ipv4.conf.all.rp_filter=1",
        "net.ipv4.conf.default.rp_filter=1",
        "net.ipv4.conf.all.accept_redirects=0",
        "net.ipv4.conf.default.accept_redirects=0",
        "net.ipv4.conf.all.send_redirects=0",
        "net.ipv4.ip_forward=0",
    ]
    for param in sysctls:
        run_cmd(["sysctl", "-w", param], ctx)
