"""Configuracao do Grafana via Helm com datasource e dashboards provisionados."""

from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, write_file


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Grafana via Helm...")

    admin_password = typer.prompt("Senha admin do Grafana", default="admin")
    ingress_host = typer.prompt("Host para acessar o Grafana", default="grafana.local")
    ingress_class = typer.prompt("IngressClass", default="traefik")
    tls_secret = typer.prompt("Secret TLS (cert-manager)", default="grafana-tls")

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
  size: 10Gi
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
