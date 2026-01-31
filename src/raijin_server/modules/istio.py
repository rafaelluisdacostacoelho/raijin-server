"""Instalacao do Istio usando istioctl com configuracoes production-ready."""

import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd, write_file


ISTIO_PROFILES = ["default", "demo", "minimal", "ambient", "empty"]


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


def _check_metallb_installed(ctx: ExecutionContext) -> bool:
    """Verifica se MetalLB está instalado no cluster."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "metallb-controller", "-n", "metallb-system"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_existing_istio(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Istio."""
    result = run_cmd(
        ["kubectl", "get", "namespace", "istio-system"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_istio(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Istio."""
    typer.echo("Removendo instalacao anterior do Istio...")
    
    run_cmd(
        ["istioctl", "uninstall", "--purge", "-y"],
        ctx,
        check=False,
    )
    
    run_cmd(
        ["kubectl", "delete", "namespace", "istio-system", "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_istio_ready(ctx: ExecutionContext, timeout: int = 300) -> bool:
    """Aguarda pods do Istio ficarem Ready."""
    typer.echo("Aguardando pods do Istio ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "istio-system", "get", "pods",
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
                
                if pods and all(phase in ("Running", "Succeeded") for _, phase in pods):
                    typer.secho(f"  Todos os {len(pods)} pods Ready.", fg=typer.colors.GREEN)
                    return True
                
                pending = [name for name, phase in pods if phase not in ("Running", "Succeeded")]
                if pending:
                    typer.echo(f"  Aguardando: {', '.join(pending[:3])}...")
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando pods do Istio.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("istioctl", ctx, install_hint="Baixe em https://istio.io/latest/docs/setup/getting-started/")
    typer.echo("Instalando Istio...")

    # Prompt opcional de limpeza
    if _check_existing_istio(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Istio detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_istio(ctx)

    # Selecao de perfil
    typer.echo(f"\nPerfis disponiveis: {', '.join(ISTIO_PROFILES)}")
    profile = typer.prompt("Perfil do Istio", default="default")
    if profile not in ISTIO_PROFILES:
        typer.secho(f"Perfil '{profile}' invalido. Usando 'default'.", fg=typer.colors.YELLOW)
        profile = "default"

    # Detectar se MetalLB está instalado
    has_metallb = _check_metallb_installed(ctx)
    
    # Se não tem MetalLB, avisar e usar NodePort
    if not has_metallb:
        typer.secho(
            "\n⚠ MetalLB não detectado. O IngressGateway será configurado como NodePort.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Para usar LoadBalancer, instale MetalLB primeiro: raijin-server install metallb")
        service_type = "NodePort"
    else:
        typer.secho("\n✓ MetalLB detectado. IngressGateway usará LoadBalancer.", fg=typer.colors.GREEN)
        service_type = "LoadBalancer"

    node_name = _detect_node_name(ctx)
    
    # Criar arquivo IstioOperator YAML (mais confiável que --set para configurações complexas)
    istio_config = f"""apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  namespace: istio-system
spec:
  profile: {profile}
  components:
    pilot:
      enabled: true
      k8s:
        tolerations:
          - key: node-role.kubernetes.io/control-plane
            operator: Exists
            effect: NoSchedule
          - key: node-role.kubernetes.io/master
            operator: Exists
            effect: NoSchedule
        nodeSelector:
          kubernetes.io/hostname: {node_name}
    ingressGateways:
      - name: istio-ingressgateway
        enabled: true
        k8s:
          tolerations:
            - key: node-role.kubernetes.io/control-plane
              operator: Exists
              effect: NoSchedule
            - key: node-role.kubernetes.io/master
              operator: Exists
              effect: NoSchedule
          nodeSelector:
            kubernetes.io/hostname: {node_name}
          service:
            type: {service_type}
  values:
    global:
      proxy:
        holdApplicationUntilProxyStarts: true
"""

    config_path = Path("/tmp/raijin-istio-config.yaml")
    write_file(config_path, istio_config, ctx)
    
    # Instala usando o arquivo de configuração
    # Nota: istioctl não tem --timeout, ele usa readiness probes internamente
    install_cmd = [
        "istioctl", "install",
        "-f", str(config_path),
        "-y",
    ]
    
    run_cmd(install_cmd, ctx)
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_istio_ready(ctx)
    
    # Pergunta sobre injection
    enable_injection = typer.confirm(
        "Habilitar sidecar injection automatico no namespace 'default'?",
        default=True,
    )
    if enable_injection:
        run_cmd(
            ["kubectl", "label", "namespace", "default", "istio-injection=enabled", "--overwrite"],
            ctx,
        )
    
    typer.secho("\n✓ Istio instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    
    if service_type == "NodePort":
        typer.echo("\n📌 Acesso ao Istio IngressGateway (NodePort):")
        typer.echo("  kubectl get svc -n istio-system istio-ingressgateway")
        typer.echo("\nPara expor via LoadBalancer, instale MetalLB:")
        typer.echo("  raijin-server install metallb")
    else:
        typer.echo("\n📌 Acesso ao Istio IngressGateway (LoadBalancer):")
        typer.echo("  kubectl get svc -n istio-system istio-ingressgateway")
        typer.echo("  Aguarde o EXTERNAL-IP ser atribuido pelo MetalLB")
