"""Configuracao do Kong Gateway via Helm com configuracoes production-ready."""

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


def _check_metallb_installed(ctx: ExecutionContext) -> bool:
    """Verifica se MetalLB está instalado no cluster."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "metallb-controller", "-n", "metallb-system"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_cert_manager_installed(ctx: ExecutionContext) -> bool:
    """Verifica se cert-manager está instalado no cluster."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "cert-manager", "-n", "cert-manager"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_existing_kong(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Kong."""
    result = run_cmd(
        ["helm", "status", "kong", "-n", "kong"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_orphan_crds(ctx: ExecutionContext) -> list[str]:
    """Detecta CRDs orfaos do Kong (sem ownership do Helm)."""
    result = run_cmd(
        ["kubectl", "get", "crd", "-o", "name"],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        return []
    
    kong_crds = []
    for line in (result.stdout or "").strip().split("\n"):
        if "konghq.com" in line:
            # Extrai nome do CRD
            crd_name = line.replace("customresourcedefinition.apiextensions.k8s.io/", "")
            kong_crds.append(crd_name)
    
    return kong_crds


def _cleanup_orphan_crds(ctx: ExecutionContext, crds: list[str]) -> None:
    """Remove CRDs orfaos do Kong."""
    typer.echo(f"Removendo {len(crds)} CRDs orfaos do Kong...")
    
    for crd in crds:
        run_cmd(
            ["kubectl", "delete", "crd", crd, "--ignore-not-found"],
            ctx,
            check=False,
        )
    
    time.sleep(3)
    typer.secho("  CRDs orfaos removidos.", fg=typer.colors.GREEN)


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
    
    # Verificar CRDs orfaos (sem ownership do Helm)
    orphan_crds = _check_orphan_crds(ctx)
    if orphan_crds:
        typer.secho(
            f"\n⚠️  Detectados {len(orphan_crds)} CRDs orfaos do Kong (sem ownership do Helm):",
            fg=typer.colors.YELLOW,
        )
        for crd in orphan_crds[:5]:
            typer.echo(f"    - {crd}")
        if len(orphan_crds) > 5:
            typer.echo(f"    ... e mais {len(orphan_crds) - 5}")
        
        cleanup_crds = typer.confirm(
            "\nRemover CRDs orfaos para permitir instalacao limpa?",
            default=True,
        )
        if cleanup_crds:
            _cleanup_orphan_crds(ctx, orphan_crds)
        else:
            typer.secho(
                "AVISO: A instalacao pode falhar devido aos CRDs orfaos.",
                fg=typer.colors.YELLOW,
            )

    # Detectar dependencias
    has_metallb = _check_metallb_installed(ctx)
    has_cert_manager = _check_cert_manager_installed(ctx)

    # Tipo de servico baseado na presenca do MetalLB
    if has_metallb:
        typer.secho("✓ MetalLB detectado. Kong usará LoadBalancer.", fg=typer.colors.GREEN)
        service_type = "LoadBalancer"
    else:
        typer.secho("⚠ MetalLB não detectado. Kong usará NodePort.", fg=typer.colors.YELLOW)
        service_type = "NodePort"

    if has_cert_manager:
        typer.secho("✓ cert-manager detectado. TLS automático disponível.", fg=typer.colors.GREEN)
    else:
        typer.secho("⚠ cert-manager não detectado. Configure TLS manualmente.", fg=typer.colors.YELLOW)

    # Configuracoes interativas
    enable_admin = typer.confirm("Habilitar Admin API (para gerenciamento)?", default=True)
    enable_metrics = typer.confirm("Habilitar métricas Prometheus?", default=True)
    db_mode = typer.prompt(
        "Modo de banco de dados (dbless/postgres)",
        default="dbless",
    )
    
    node_name = _detect_node_name(ctx)

    # Usar arquivo YAML para configurações complexas (mais confiável que --set)
    values_yaml = f"""env:
  database: {db_mode}

ingressController:
  installCRDs: true
  enabled: true

proxy:
  enabled: true
  type: {service_type}
  http:
    enabled: true
    containerPort: 8000
    servicePort: 80
  tls:
    enabled: true
    containerPort: 8443
    servicePort: 443

admin:
  enabled: {str(enable_admin).lower()}
  type: ClusterIP
  http:
    enabled: true

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

    # Adicionar métricas se habilitado
    if enable_metrics:
        values_yaml += """
serviceMonitor:
  enabled: true
  namespace: kong
  labels:
    release: kube-prometheus-stack

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8100"
"""

    values_path = Path("/tmp/raijin-kong-values.yaml")
    write_file(values_path, values_yaml, ctx)

    run_cmd(["kubectl", "create", "namespace", "kong"], ctx, check=False)
    
    helm_upgrade_install(
        release="kong",
        chart="kong",
        namespace="kong",
        repo="kong",
        repo_url="https://charts.konghq.com",
        ctx=ctx,
        values=[],
        extra_args=["-f", str(values_path)],
    )
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_kong_ready(ctx)
    
    # Mostra informacoes uteis
    typer.secho("\n✓ Kong Gateway instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    
    typer.echo("\n📌 Acesso ao Kong Proxy:")
    if service_type == "LoadBalancer":
        typer.echo("  kubectl -n kong get svc kong-kong-proxy  # Aguarde EXTERNAL-IP")
    else:
        typer.echo("  kubectl -n kong get svc kong-kong-proxy  # Use NodePort")
    
    if enable_admin:
        typer.echo("\n📌 Admin API (port-forward):")
        typer.echo("  kubectl -n kong port-forward svc/kong-kong-admin 8001:8001")
        typer.echo("  curl http://localhost:8001/status")
    
    if enable_metrics:
        typer.echo("\n📌 Métricas Prometheus:")
        typer.echo("  ServiceMonitor criado - métricas serão coletadas automaticamente")
    
    if has_cert_manager:
        typer.echo("\n📌 TLS com cert-manager (exemplo de Ingress):")
        typer.echo("""  ---
  apiVersion: networking.k8s.io/v1
  kind: Ingress
  metadata:
    name: my-api
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
      konghq.com/strip-path: "true"
  spec:
    ingressClassName: kong
    tls:
      - hosts: [api.example.com]
        secretName: api-tls
    rules:
      - host: api.example.com
        http:
          paths:
            - path: /
              pathType: Prefix
              backend:
                service:
                  name: my-service
                  port:
                    number: 80""")
