"""Backup e restore com Velero (production-ready)."""

import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd
from raijin_server.minio_utils import get_or_create_minio_user


def _create_velero_credentials_file(ctx: ExecutionContext) -> str:
    """Cria arquivo de credenciais para Velero com usuário MinIO dedicado.
    
    Returns:
        Caminho para o arquivo de credenciais
    """
    typer.echo("\nConfigurando credenciais MinIO para Velero...")
    
    # Cria usuário MinIO específico para Velero
    access_key, secret_key = get_or_create_minio_user(
        ctx=ctx,
        app_name="velero",
        buckets=["velero-backups"],
        namespace="velero",
    )
    
    # Cria arquivo de credenciais no formato esperado pelo Velero
    credentials_path = Path("/etc/velero/credentials")
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    
    credentials_content = f"""[default]
aws_access_key_id = {access_key}
aws_secret_access_key = {secret_key}
"""
    
    if not ctx.dry_run:
        credentials_path.write_text(credentials_content)
        # Protege o arquivo
        credentials_path.chmod(0o600)
        typer.secho(f"  ✓ Credenciais salvas em {credentials_path}", fg=typer.colors.GREEN)
    
    return str(credentials_path)


def _check_existing_velero(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Velero."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "velero", "-n", "velero"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_velero(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Velero."""
    typer.echo("Removendo instalacao anterior do Velero...")
    
    run_cmd(
        ["velero", "uninstall", "--force"],
        ctx,
        check=False,
    )
    
    # Remove schedules
    run_cmd(
        ["velero", "schedule", "delete", "--all", "--confirm"],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_velero_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Velero ficarem Ready."""
    typer.echo("Aguardando pods do Velero ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "velero", "get", "pods",
                "-l", "component=velero",
                "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.phase} {end}",
            ],
            ctx,
            check=False,
        )
        
        if result.returncode == 0:
            output = (result.stdout or "").strip()
            if output:
                pods = []
                for item in output.split():
                    if "=" in item:
                        parts = item.rsplit("=", 1)
                        if len(parts) == 2:
                            pods.append((parts[0], parts[1]))
                
                if pods and all(phase == "Running" for _, phase in pods):
                    typer.secho("  Velero Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Velero.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("velero", ctx, install_hint="Instale o binario do Velero: https://velero.io/docs/main/basic-install/")

    # Prompt opcional de limpeza
    if _check_existing_velero(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Velero detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_velero(ctx)

    typer.echo("Instalando Velero no cluster...")
    
    provider = typer.prompt("Provider (aws, azure, gcp)", default="aws")
    bucket = typer.prompt("Bucket para backups", default="velero-backups")
    region = typer.prompt("Region", default="us-east-1")
    s3_url = typer.prompt("S3 URL (para MinIO usar http://minio.minio.svc:9000)", default="http://minio.minio.svc:9000")
    
    # Cria credenciais automaticamente usando usuário MinIO dedicado
    use_auto_credentials = typer.confirm(
        "Criar credenciais MinIO automaticamente (usuário dedicado)?",
        default=True,
    )
    
    if use_auto_credentials:
        secret_file = _create_velero_credentials_file(ctx)
    else:
        secret_file = typer.prompt("Arquivo de credenciais (secret-file)", default="/etc/velero/credentials")
    
    use_restic = typer.confirm("Habilitar Restic/Kopia para backups de PV?", default=True)
    schedule = typer.prompt("Schedule cron para backups (ex: '0 2 * * *')", default="0 2 * * *")

    # Build velero install command with tolerations
    install_cmd = [
        "velero",
        "install",
        "--provider", provider,
        "--bucket", bucket,
        "--secret-file", secret_file,
        "--backup-location-config", f"region={region},s3Url={s3_url}",
        "--pod-annotations", "prometheus.io/scrape=true,prometheus.io/port=8085",
    ]

    # Add plugin based on provider
    if provider == "aws":
        install_cmd.extend(["--plugins", "velero/velero-plugin-for-aws:v1.8.0"])
    elif provider == "azure":
        install_cmd.extend(["--plugins", "velero/velero-plugin-for-microsoft-azure:v1.8.0"])
    elif provider == "gcp":
        install_cmd.extend(["--plugins", "velero/velero-plugin-for-gcp:v1.8.0"])

    if use_restic:
        install_cmd.append("--use-node-agent")

    # For MinIO/S3-compatible, disable SSL verification if using http
    if s3_url.startswith("http://"):
        install_cmd.extend(["--backup-location-config", "s3ForcePathStyle=true"])

    run_cmd(install_cmd, ctx)

    # Apply tolerations patch
    typer.echo("Aplicando tolerations para control-plane...")
    tolerations_patch = """spec:
  template:
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
        - key: node-role.kubernetes.io/master
          operator: Exists
          effect: NoSchedule"""

    run_cmd(
        ["kubectl", "-n", "velero", "patch", "deployment", "velero",
         "--type=strategic", "-p", tolerations_patch],
        ctx,
        check=False,
    )

    if not ctx.dry_run:
        _wait_for_velero_ready(ctx)

    typer.echo("Criando schedule de backup padrao...")
    run_cmd([
        "velero",
        "create",
        "schedule",
        "raijin-daily",
        "--schedule", schedule,
        "--include-namespaces", "*",
        "--ttl", "720h",  # 30 dias
    ], ctx, check=False)

    typer.secho("\n✓ Velero instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nComandos uteis:")
    typer.echo("  velero backup get                    # Listar backups")
    typer.echo("  velero backup create manual-backup   # Criar backup manual")
    typer.echo("  velero restore create --from-backup <name>  # Restaurar")
    typer.echo("  velero schedule get                  # Listar schedules")
