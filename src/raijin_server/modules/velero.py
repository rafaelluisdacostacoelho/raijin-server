"""Backup e restore com Velero."""

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("velero", ctx, install_hint="Instale o binario do Velero.")

    typer.echo("Instalando Velero no cluster...")
    provider = typer.prompt("Provider", default="aws")
    bucket = typer.prompt("Bucket", default="velero-backups")
    region = typer.prompt("Region", default="us-east-1")
    s3_url = typer.prompt("S3 URL", default="https://s3.amazonaws.com")
    secret_file = typer.prompt("Arquivo de credenciais (secret-file)", default="/etc/velero/credentials")
    schedule = typer.prompt("Schedule cron para backups (ex: '0 2 * * *')", default="0 2 * * *")

    run_cmd(
        [
            "velero",
            "install",
            "--provider",
            provider,
            "--bucket",
            bucket,
            "--secret-file",
            secret_file,
            "--backup-location-config",
            f"region={region},s3Url={s3_url}",
            "--use-restic",
        ],
        ctx,
    )

    typer.echo("Criando schedule de backup padrao...")
    run_cmd([
        "velero",
        "create",
        "schedule",
        "raijin-daily",
        "--schedule",
        schedule,
        "--include-namespaces",
        "*",
    ], ctx, check=False)
