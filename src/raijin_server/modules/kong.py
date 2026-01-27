"""Configuracao do Kong via Helm."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Kong via Helm...")
    helm_upgrade_install(
        release="kong",
        chart="kong",
        namespace="kong",
        repo="kong",
        repo_url="https://charts.konghq.com",
        ctx=ctx,
        values=["ingressController.installCRDs=false"],
    )
