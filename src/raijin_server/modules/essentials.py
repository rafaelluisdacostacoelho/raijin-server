"""Instalacao de ferramentas basicas do sistema."""

import typer

from raijin_server.utils import ExecutionContext, apt_install, apt_update, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando ferramentas essenciais...")
    apt_update(ctx)
    apt_install(
        [
            "curl",
            "wget",
            "git",
            "gnupg",
            "lsb-release",
            "ca-certificates",
            "apt-transport-https",
            "htop",
            "net-tools",
            "vim",
            "jq",
            "unzip",
        ],
        ctx,
    )
    run_cmd(["timedatectl", "set-ntp", "true"], ctx)
