"""Configuracao do Grafana via Helm com datasource e dashboards provisionados."""

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


def _check_existing_grafana(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Grafana."""
    result = run_cmd(
        ["helm", "status", "grafana", "-n", "observability"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_grafana(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Grafana."""
    typer.echo("Removendo instalacao anterior do Grafana...")
    
    run_cmd(
        ["helm", "uninstall", "grafana", "-n", "observability"],
        ctx,
        check=False,
    )
    
    remove_data = typer.confirm("Remover PVCs (dados persistentes)?", default=False)
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "observability", "delete", "pvc", "-l", "app.kubernetes.io/name=grafana"],
            ctx,
            check=False,
        )
    
    time.sleep(5)


def _wait_for_grafana_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Grafana ficarem Ready."""
    typer.echo("Aguardando pods do Grafana ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "observability", "get", "pods",
                "-l", "app.kubernetes.io/name=grafana",
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
                    typer.secho("  Grafana Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Grafana.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Grafana via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_grafana(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Grafana detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_grafana(ctx)

    admin_password = typer.prompt("Senha admin do Grafana", default="admin")
    ingress_host = typer.prompt("Host para acessar o Grafana", default="grafana.local")
    ingress_class = typer.prompt("IngressClass", default="traefik")
    tls_secret = typer.prompt("Secret TLS (cert-manager)", default="grafana-tls")
    persistence_size = typer.prompt("Tamanho do storage", default="10Gi")

    node_name = _detect_node_name(ctx)

    values_yaml = f"""adminPassword: {admin_password}
service:
  type: ClusterIP
ingress:
  enabled: true
  ingressClassName: {ingress_class}
  hosts:
    - {ingress_host}
  tls:
    - secretName: {tls_secret}
      hosts:
        - {ingress_host}
persistence:
  enabled: true
  size: {persistence_size}
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
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://kube-prometheus-stack-prometheus.observability.svc:9090
        isDefault: true
        jsonData:
          timeInterval: 30s
      - name: Loki
        type: loki
        access: proxy
        url: http://loki.observability.svc:3100
dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards/default
dashboards:
  default:
    kubernetes:
      gnetId: 6417
      revision: 1
      datasource: Prometheus
    node-exporter:
      gnetId: 1860
      revision: 27
      datasource: Prometheus
"""

    values_path = Path("/tmp/raijin-grafana-values.yaml")
    write_file(values_path, values_yaml, ctx)

    run_cmd(["kubectl", "create", "namespace", "observability"], ctx, check=False)

    helm_upgrade_install(
        release="grafana",
        chart="grafana",
        namespace="observability",
        repo="grafana",
        repo_url="https://grafana.github.io/helm-charts",
        ctx=ctx,
        values=[],
        extra_args=["-f", str(values_path)],
    )

    if not ctx.dry_run:
        _wait_for_grafana_ready(ctx)

    typer.secho("\n✓ Grafana instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"\nAcesse: https://{ingress_host}")
    typer.echo("Usuario: admin")
    typer.echo(f"Senha: {admin_password}")
    typer.echo("\nPara port-forward local:")
    typer.echo("  kubectl -n observability port-forward svc/grafana 3000:80")
