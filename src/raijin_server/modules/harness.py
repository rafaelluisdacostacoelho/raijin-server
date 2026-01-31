"""Instalacao do Harness Delegate via Helm (production-ready)."""

import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd, write_file


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


def _check_existing_delegate(ctx: ExecutionContext, namespace: str, delegate_name: str) -> bool:
    """Verifica se existe instalacao do Harness Delegate."""
    result = run_cmd(
        ["helm", "status", delegate_name, "-n", namespace],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_delegate(ctx: ExecutionContext, namespace: str, delegate_name: str) -> None:
    """Remove instalacao anterior do Harness Delegate."""
    typer.echo("Removendo instalacao anterior do Harness Delegate...")
    
    run_cmd(
        ["helm", "uninstall", delegate_name, "-n", namespace],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_delegate_ready(ctx: ExecutionContext, namespace: str, delegate_name: str, timeout: int = 180) -> bool:
    """Aguarda pods do Harness Delegate ficarem Ready."""
    typer.echo("Aguardando pods do Harness Delegate ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
                "-l", f"app.kubernetes.io/name={delegate_name}",
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
                    typer.secho("  Harness Delegate Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Harness Delegate.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("helm", ctx, install_hint="Instale helm para implantar o delegate.")

    typer.echo("Instalando Harness Delegate via Helm...")
    account_id = typer.prompt("Harness accountId")
    org_id = typer.prompt("Org ID", default="default")
    project_id = typer.prompt("Project ID", default="default")
    delegate_name = typer.prompt("Delegate name", default="raijin-delegate")
    namespace = typer.prompt("Namespace", default="harness-delegate")
    delegate_token = typer.prompt("Delegate token", hide_input=True)
    replicas = typer.prompt("Numero de replicas", default="1")

    # Prompt opcional de limpeza
    if _check_existing_delegate(ctx, namespace, delegate_name):
        cleanup = typer.confirm(
            "Instalacao anterior do Harness Delegate detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_delegate(ctx, namespace, delegate_name)

    node_name = _detect_node_name(ctx)

    run_cmd(
        ["helm", "repo", "add", "harness", "https://app.harness.io/storage/harness-download/delegate-helm-chart/"],
        ctx,
    )
    run_cmd(["helm", "repo", "update"], ctx)

    # Create values file with tolerations
    values_yaml = f"""delegateName: {delegate_name}
accountId: {account_id}
delegateToken: {delegate_token}
orgId: {org_id}
projectId: {project_id}
replicaCount: {replicas}
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
    memory: 1Gi
"""

    values_path = Path("/tmp/raijin-harness-values.yaml")
    write_file(values_path, values_yaml, ctx)

    cmd = [
        "helm",
        "upgrade",
        "--install",
        delegate_name,
        "harness/harness-delegate-ng",
        "-n",
        namespace,
        "--create-namespace",
        "-f",
        str(values_path),
    ]

    run_cmd(cmd, ctx, mask_output=True, display_override="helm upgrade --install <delegate> harness/harness-delegate-ng ...")

    if not ctx.dry_run:
        _wait_for_delegate_ready(ctx, namespace, delegate_name)

    typer.secho("\n✓ Harness Delegate instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"\nO delegate '{delegate_name}' deve aparecer no Harness em alguns minutos.")
    typer.echo("\nPara verificar status:")
    typer.echo(f"  kubectl -n {namespace} get pods")
    typer.echo(f"  kubectl -n {namespace} logs -l app.kubernetes.io/name={delegate_name}")
