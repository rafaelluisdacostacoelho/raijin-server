"""Provisiona MetalLB (L2) com pool de IPs para LoadBalancer em ambientes bare metal."""

import base64
import socket
import time

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, run_cmd


def _detect_node_name(ctx: ExecutionContext) -> str:
    """Tenta obter o nome do node via kubectl; fallback para hostname local."""

    result = run_cmd(
        [
            "kubectl",
            "get",
            "nodes",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        node_name = (result.stdout or "").strip()
        if node_name:
            return node_name
    return socket.gethostname()


def _uninstall_metallb(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do MetalLB completamente."""
    typer.echo("Removendo instalacao anterior do MetalLB...")
    
    # Helm uninstall
    run_cmd(
        ["helm", "uninstall", "metallb", "-n", "metallb-system"],
        ctx,
        check=False,
    )
    
    # Remove CRDs que podem ficar orfaos
    run_cmd(
        ["kubectl", "delete", "crd", 
         "ipaddresspools.metallb.io",
         "l2advertisements.metallb.io",
         "bgpadvertisements.metallb.io",
         "bgppeers.metallb.io",
         "bfdprofiles.metallb.io",
         "communities.metallb.io",
         "servicel2statuses.metallb.io",
         "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    # Remove namespace se existir
    run_cmd(
        ["kubectl", "delete", "namespace", "metallb-system", "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    # Aguarda limpeza
    time.sleep(5)


def _check_existing_metallb(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do MetalLB."""
    result = run_cmd(
        ["helm", "status", "metallb", "-n", "metallb-system"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _wait_for_pods_running(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda todos os pods do MetalLB estarem Running."""
    typer.echo("Aguardando pods do MetalLB ficarem Running...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        # Usa separador simples para evitar problemas com \n literal
        result = run_cmd(
            [
                "kubectl", "-n", "metallb-system", "get", "pods",
                "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.phase} {end}",
            ],
            ctx,
            check=False,
        )
        
        if result.returncode != 0:
            time.sleep(5)
            continue
            
        output = (result.stdout or "").strip()
        if not output:
            time.sleep(5)
            continue
        
        pods = []
        for item in output.split():
            if "=" in item:
                parts = item.rsplit("=", 1)
                if len(parts) == 2:
                    pods.append((parts[0], parts[1]))
        
        if not pods:
            time.sleep(5)
            continue
        
        all_running = all(phase == "Running" for _, phase in pods)
        if all_running and pods:
            typer.secho(f"  Todos os {len(pods)} pods Running.", fg=typer.colors.GREEN)
            return True
        
        # Mostra status atual
        pending = [name for name, phase in pods if phase != "Running"]
        if pending:
            typer.echo(f"  Aguardando: {', '.join(pending[:3])}...")
        
        time.sleep(10)
    
    # Timeout - mostra diagnostico
    typer.secho("  Timeout esperando pods. Diagnostico:", fg=typer.colors.YELLOW)
    run_cmd(["kubectl", "-n", "metallb-system", "get", "pods", "-o", "wide"], ctx, check=False)
    run_cmd(["kubectl", "-n", "metallb-system", "get", "events", "--sort-by=.lastTimestamp"], ctx, check=False)
    return False


def _wait_for_webhook_ready(ctx: ExecutionContext, timeout: int = 120) -> bool:
    """Aguarda webhook estar respondendo."""
    typer.echo("Aguardando webhook do MetalLB...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "metallb-system", "get", "endpoints",
                "metallb-webhook-service", "-o", "jsonpath={.subsets[0].addresses[0].ip}",
            ],
            ctx,
            check=False,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            typer.secho("  Webhook disponivel.", fg=typer.colors.GREEN)
            return True
        time.sleep(5)
    
    typer.secho("  Webhook nao ficou disponivel.", fg=typer.colors.YELLOW)
    return False


def _apply_pool_with_retry(manifest: str, ctx: ExecutionContext, max_attempts: int = 12) -> bool:
    """Aplica IPAddressPool/L2Advertisement com retry."""
    typer.echo("Aplicando IPAddressPool e L2Advertisement...")
    
    encoded = base64.b64encode(manifest.encode()).decode()
    
    for attempt in range(1, max_attempts + 1):
        result = run_cmd(
            f"echo '{encoded}' | base64 -d | kubectl apply -f -",
            ctx,
            use_shell=True,
            check=False,
        )
        if result.returncode == 0:
            typer.secho("  Pool e L2Advertisement aplicados.", fg=typer.colors.GREEN)
            return True
        
        stderr = (result.stderr or "").lower()
        if "webhook" in stderr or "connection refused" in stderr:
            typer.echo(f"  Webhook nao pronto, tentativa {attempt}/{max_attempts}...")
            time.sleep(10)
        else:
            typer.secho(f"  Erro: {result.stderr}", fg=typer.colors.RED)
            return False
    
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando MetalLB via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_metallb(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do MetalLB detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_metallb(ctx)

    pool = typer.prompt(
        "Pool de IPs (range ou CIDR) para services LoadBalancer",
        default="192.168.1.100-192.168.1.250",
    )

    node_name = _detect_node_name(ctx)

    values = [
        # Permite agendar em control-plane de cluster single-node
        "controller.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "controller.tolerations[0].operator=Exists",
        "controller.tolerations[0].effect=NoSchedule",
        "controller.tolerations[1].key=node-role.kubernetes.io/master",
        "controller.tolerations[1].operator=Exists",
        "controller.tolerations[1].effect=NoSchedule",
        "speaker.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "speaker.tolerations[0].operator=Exists",
        "speaker.tolerations[0].effect=NoSchedule",
        "speaker.tolerations[1].key=node-role.kubernetes.io/master",
        "speaker.tolerations[1].operator=Exists",
        "speaker.tolerations[1].effect=NoSchedule",
        # nodeSelector com chave escapada
        f"controller.nodeSelector.kubernetes\\.io/hostname={node_name}",
        f"speaker.nodeSelector.kubernetes\\.io/hostname={node_name}",
    ]

    # Instala do zero
    helm_upgrade_install(
        release="metallb",
        chart="metallb",
        namespace="metallb-system",
        repo="metallb",
        repo_url="https://metallb.github.io/metallb",
        ctx=ctx,
        values=values,
    )

    # Aguarda pods estarem Running
    if not _wait_for_pods_running(ctx):
        ctx.errors.append("Pods do MetalLB nao subiram - verifique taints/recursos do cluster")
        return

    # Aguarda webhook
    if not _wait_for_webhook_ready(ctx):
        typer.secho("Continuando mesmo sem confirmacao do webhook...", fg=typer.colors.YELLOW)

    # Aplica pool
    manifest = f"""
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: raijin-pool
  namespace: metallb-system
spec:
  addresses:
    - {pool}
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: raijin-l2
  namespace: metallb-system
spec:
  ipAddressPools:
    - raijin-pool
"""

    if not _apply_pool_with_retry(manifest, ctx):
        ctx.errors.append("Falha ao aplicar IPAddressPool/L2Advertisement")
        return

    typer.secho("\n✓ MetalLB instalado. Services LoadBalancer usarao o pool informado.", fg=typer.colors.GREEN, bold=True)
