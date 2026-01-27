"""Deploy do MinIO via Helm."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando MinIO via Helm (modo standalone)...")
    helm_upgrade_install(
        release="minio",
        chart="minio",
        namespace="minio",
        repo="minio",
        repo_url="https://charts.min.io/",
        ctx=ctx,
        values=["mode=standalone"],
    )
