"""Deploy do MinIO via Helm com configuracoes production-ready."""

import secrets
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


def _generate_secret(length: int = 32) -> str:
    """Gera secret aleatório seguro."""
    return secrets.token_urlsafe(length)[:length]


def _check_existing_minio(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do MinIO."""
    result = run_cmd(
        ["helm", "status", "minio", "-n", "minio"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_minio(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do MinIO."""
    typer.echo("Removendo instalacao anterior do MinIO...")
    
    run_cmd(
        ["helm", "uninstall", "minio", "-n", "minio"],
        ctx,
        check=False,
    )
    
    # Pergunta se quer remover PVCs (dados)
    remove_data = typer.confirm(
        "Remover PVCs (dados persistentes)?",
        default=False,
    )
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "minio", "delete", "pvc", "--all"],
            ctx,
            check=False,
        )
    
    run_cmd(
        ["kubectl", "delete", "namespace", "minio", "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_minio_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do MinIO ficarem Ready."""
    typer.echo("Aguardando pods do MinIO ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "minio", "get", "pods",
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
    
    typer.secho("  Timeout aguardando pods do MinIO.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando MinIO via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_minio(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do MinIO detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_minio(ctx)

    # Configuracoes interativas
    mode = typer.prompt(
        "Modo de operacao (standalone/distributed)",
        default="standalone",
    )
    
    root_user = typer.prompt("Root user (admin)", default="minio-admin")
    root_password = typer.prompt(
        "Root password (deixe vazio para gerar)",
        default="",
        hide_input=True,
    )
    if not root_password:
        root_password = _generate_secret(24)
        typer.secho(f"  Password gerado: {root_password}", fg=typer.colors.CYAN)
    
    persistence_size = typer.prompt("Tamanho do storage (ex: 10Gi, 50Gi)", default="10Gi")
    enable_console = typer.confirm("Habilitar Console Web?", default=True)
    
    node_name = _detect_node_name(ctx)
    
    values = [
        f"mode={mode}",
        f"rootUser={root_user}",
        f"rootPassword={root_password}",
        # Persistence
        "persistence.enabled=true",
        f"persistence.size={persistence_size}",
        # Resources (production defaults)
        "resources.requests.memory=512Mi",
        "resources.requests.cpu=250m",
        "resources.limits.memory=1Gi",
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
    
    # Console
    if enable_console:
        values.extend([
            "consoleService.type=ClusterIP",
            "consoleIngress.enabled=false",
        ])
    
    helm_upgrade_install(
        release="minio",
        chart="minio",
        namespace="minio",
        repo="minio",
        repo_url="https://charts.min.io/",
        ctx=ctx,
        values=values,
    )
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_minio_ready(ctx)
    
    # Mostra informacoes uteis
    typer.secho("\n✓ MinIO instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nCredenciais:")
    typer.echo(f"  Root User: {root_user}")
    typer.echo(f"  Root Password: {root_password}")
    typer.echo("\nPara acessar a API (port-forward):")
    typer.echo("  kubectl -n minio port-forward svc/minio 9000:9000")
    if enable_console:
        typer.echo("\nPara acessar o Console Web (port-forward):")
        typer.echo("  kubectl -n minio port-forward svc/minio-console 9001:9001")
        typer.echo("  Acesse: http://localhost:9001")
