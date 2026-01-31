"""Configuracao do Kong Gateway via Helm com configuracoes production-ready."""

import socket
import time

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, run_cmd


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


def _check_existing_kong(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Kong."""
    result = run_cmd(
        ["helm", "status", "kong", "-n", "kong"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_kong(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Kong."""
    typer.echo("Removendo instalacao anterior do Kong...")
    
    run_cmd(
        ["helm", "uninstall", "kong", "-n", "kong"],
        ctx,
        check=False,
    )
    
    run_cmd(
        ["kubectl", "delete", "namespace", "kong", "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_kong_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Kong ficarem Ready."""
    typer.echo("Aguardando pods do Kong ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "kong", "get", "pods",
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
                    typer.secho(f"  Todos os {len(pods)} pods Running.", fg=typer.colors.GREEN)
                    return True
                
                pending = [name for name, phase in pods if phase != "Running"]
                if pending:
                    typer.echo(f"  Aguardando: {', '.join(pending[:3])}...")
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando pods do Kong.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Kong Gateway via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_kong(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Kong detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_kong(ctx)

    # Configuracoes interativas
    enable_admin = typer.confirm("Habilitar Admin API (para gerenciamento)?", default=True)
    db_mode = typer.prompt(
        "Modo de banco de dados (dbless/postgres)",
        default="dbless",
    )
    
    node_name = _detect_node_name(ctx)
    
    values = [
        # Modo de operacao
        f"env.database={db_mode}",
        # Ingress Controller
        "ingressController.installCRDs=true",
        "ingressController.enabled=true",
        # Proxy service
        "proxy.enabled=true",
        "proxy.type=LoadBalancer",
        # Tolerations para control-plane
        "tolerations[0].key=node-role.kubernetes.io/control-plane",
        "tolerations[0].operator=Exists",
        "tolerations[0].effect=NoSchedule",
        "tolerations[1].key=node-role.kubernetes.io/master",
        "tolerations[1].operator=Exists",
        "tolerations[1].effect=NoSchedule",
        # NodeSelector
        f"nodeSelector.kubernetes\\.io/hostname={node_name}",
    ]
    
    # Admin API
    if enable_admin:
        values.extend([
            "admin.enabled=true",
            "admin.type=ClusterIP",
            "admin.http.enabled=true",
        ])
    else:
        values.append("admin.enabled=false")
    
    helm_upgrade_install(
        release="kong",
        chart="kong",
        namespace="kong",
        repo="kong",
        repo_url="https://charts.konghq.com",
        ctx=ctx,
        values=values,
    )
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_kong_ready(ctx)
    
    # Mostra informacoes uteis
    typer.secho("\n✓ Kong instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nPara verificar o servico:")
    typer.echo("  kubectl -n kong get svc kong-kong-proxy")
    if enable_admin:
        typer.echo("\nPara acessar Admin API (port-forward):")
        typer.echo("  kubectl -n kong port-forward svc/kong-kong-admin 8001:8001")
