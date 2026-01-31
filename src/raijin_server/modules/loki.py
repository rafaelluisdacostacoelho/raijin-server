"""Configuracao do Loki Stack via Helm (production-ready)."""

import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, run_cmd, write_file


def _detect_node_name(ctx: ExecutionContext) -> str:
    """Detecta nome do node para nodeSelector."""
    result = run_cmd(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].metadata.name}"],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        return (result.stdout or "").strip()
    return socket.gethostname()


def _check_existing_loki(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Loki."""
    result = run_cmd(
        ["helm", "status", "loki", "-n", "observability"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_loki(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Loki."""
    typer.echo("Removendo instalacao anterior do Loki...")
    
    run_cmd(
        ["helm", "uninstall", "loki", "-n", "observability"],
        ctx,
        check=False,
    )
    
    remove_data = typer.confirm("Remover PVCs (dados persistentes)?", default=False)
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "observability", "delete", "pvc", "-l", "app=loki"],
            ctx,
            check=False,
        )
    
    time.sleep(5)


def _wait_for_loki_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Loki ficarem Ready."""
    typer.echo("Aguardando pods do Loki ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "observability", "get", "pods",
                "-l", "app=loki",
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
                    typer.secho("  Loki Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Loki.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Loki Stack via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_loki(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Loki detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_loki(ctx)

    retention_hours = typer.prompt("Retencao de logs em horas", default="168")
    persistence_size = typer.prompt("Tamanho do storage", default="20Gi")

    node_name = _detect_node_name(ctx)

    values_yaml = f"""loki:
  persistence:
    enabled: true
    size: {persistence_size}
  config:
    table_manager:
      retention_deletes_enabled: true
      retention_period: {retention_hours}h
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  nodeSelector:
    kubernetes.io/hostname: {node_name}
  resources:
    requests:
      memory: 256Mi
      cpu: 100m
    limits:
      memory: 512Mi

promtail:
  enabled: true
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  resources:
    requests:
      memory: 128Mi
      cpu: 50m
    limits:
      memory: 256Mi
"""

    values_path = Path("/tmp/raijin-loki-values.yaml")
    write_file(values_path, values_yaml, ctx)

    run_cmd(["kubectl", "create", "namespace", "observability"], ctx, check=False)

    helm_upgrade_install(
        release="loki",
        chart="loki-stack",
        namespace="observability",
        repo="grafana",
        repo_url="https://grafana.github.io/helm-charts",
        ctx=ctx,
        values=[],
        extra_args=["-f", str(values_path)],
    )

    if not ctx.dry_run:
        _wait_for_loki_ready(ctx)

    typer.secho("\n✓ Loki Stack instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nPara acessar Loki via port-forward:")
    typer.echo("  kubectl -n observability port-forward svc/loki 3100:3100")
    typer.echo("\nPara verificar logs:")
    typer.echo("  curl http://localhost:3100/ready")
