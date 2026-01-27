"""Gerenciamento de firewall com UFW."""

import typer

from raijin_server.utils import ExecutionContext, apt_install, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Configurando UFW...")

    apt_install(["ufw"], ctx)
    run_cmd(["ufw", "--force", "reset"], ctx)

    regras = [
        ["ufw", "allow", "22"],
        ["ufw", "allow", "80"],
        ["ufw", "allow", "443"],
        ["ufw", "allow", "6443"],  # API server Kubernetes
        ["ufw", "allow", "2379:2380/tcp"],  # etcd
        ["ufw", "allow", "10250"],  # kubelet
    ]
    for regra in regras:
        run_cmd(regra, ctx, check=False)

    run_cmd(["ufw", "--force", "enable"], ctx)
    run_cmd(["ufw", "status", "numbered"], ctx)
