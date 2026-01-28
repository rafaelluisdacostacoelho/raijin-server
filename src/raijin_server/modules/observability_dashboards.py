"""Provisiona dashboards opinativos do Grafana e alertas padrao do Prometheus/Alertmanager."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    kubectl_apply,
    kubectl_create_ns,
    require_root,
    write_file,
)

MANIFEST_PATH = Path("/tmp/raijin-observability-dashboards.yaml")

CLUSTER_DASHBOARD = {
    "title": "Raijin Cluster Overview",
    "uid": "raijin-cluster",
    "timezone": "browser",
    "schemaVersion": 39,
    "panels": [
        {
            "type": "timeseries",
            "title": "Node CPU %",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
                    "legendFormat": "{{instance}}",
                }
            ],
        },
        {
            "type": "timeseries",
            "title": "Node Memory %",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": '((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100',
                    "legendFormat": "{{instance}}",
                }
            ],
        },
        {
            "type": "stat",
            "title": "API Server Errors (5m)",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": 'sum(rate(apiserver_request_total{code=~"5.."}[5m]))',
                }
            ],
        },
    ],
}

SLO_DASHBOARD = {
    "title": "Raijin SLO - Workloads",
    "uid": "raijin-slo",
    "schemaVersion": 39,
    "panels": [
        {
            "type": "timeseries",
            "title": "Pod Restarts (1h)",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": 'increase(kube_pod_container_status_restarts_total[1h])',
                    "legendFormat": "{{namespace}}/{{pod}}",
                }
            ],
        },
        {
            "type": "timeseries",
            "title": "Ingress HTTP 5xx Rate",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": 'sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) by (service)',
                    "legendFormat": "{{service}}",
                }
            ],
        },
        {
            "type": "gauge",
            "title": "Cluster CPU Pressure",
            "datasource": "Prometheus",
            "targets": [
                {
                    "expr": 'avg(node_pressure_cpu_waiting_seconds_total)',
                }
            ],
        },
    ],
}


def _json_block(obj: dict) -> str:
    return json.dumps(obj, indent=2, separators=(",", ": "))


def _alertmanager_block(contact_email: str, webhook_url: str) -> str:
    receivers = ["receivers:", "  - name: default"]
    if contact_email:
        receivers.append("    email_configs:")
        receivers.append(f"      - to: {contact_email}")
        receivers.append("        send_resolved: true")
    if webhook_url:
        receivers.append("    webhook_configs:")
        receivers.append(f"      - url: {webhook_url}")
        receivers.append("        send_resolved: true")
    receivers_str = "\n".join(receivers) if len(receivers) > 2 else "receivers:\n  - name: default"
    return textwrap.dedent(
        f"""
route:
  receiver: default
  group_by: ['alertname']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
{receivers_str}
"""
    ).strip()


def _build_manifest(namespace: str, contact_email: str, webhook_url: str) -> str:
    cluster_json = textwrap.indent(_json_block(CLUSTER_DASHBOARD), "    ")
    slo_json = textwrap.indent(_json_block(SLO_DASHBOARD), "    ")
    alertmanager_yaml = textwrap.indent(_alertmanager_block(contact_email, webhook_url), "    ")

    prometheus_rules = textwrap.dedent(
        f"""
        apiVersion: monitoring.coreos.com/v1
        kind: PrometheusRule
        metadata:
          name: raijin-default-alerts
          namespace: {namespace}
        spec:
          groups:
            - name: raijin-cluster-health
              rules:
                - alert: NodeDown
                  expr: kube_node_status_condition{{condition="Ready",status="true"}} == 0
                  for: 5m
                  labels:
                    severity: critical
                  annotations:
                    summary: "Node fora do cluster"
                    description: "O node {{ $labels.node }} nao reporta Ready ha 5 minutos."
                - alert: HighNodeCPU
                  expr: avg(node_load1) by (instance) > count(node_cpu_seconds_total{{mode="system"}}) by (instance)
                  for: 10m
                  labels:
                    severity: warning
                  annotations:
                    summary: "CPU elevada em {{ $labels.instance }}"
                    description: "Load1 superior ao numero de cores ha 10 minutos."
                - alert: APIServerErrorRate
                  expr: sum(rate(apiserver_request_total{{code=~"5.."}}[5m])) > 5
                  for: 5m
                  labels:
                    severity: warning
                  annotations:
                    summary: "API Server retornando 5xx"
                    description: "Taxa de erros 5xx do API Server acima de 5 req/s."
        """
    ).strip()

    grafana_cm = textwrap.dedent(
        f"""
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: grafana-dashboards-raijin
          namespace: {namespace}
          labels:
            grafana_dashboard: "1"
        data:
          cluster-overview.json: |
{cluster_json}
          slo-workloads.json: |
{slo_json}
        """
    ).strip()

    alertmanager_cm = textwrap.dedent(
        f"""
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: alertmanager-raijin
          namespace: {namespace}
          labels:
            app.kubernetes.io/name: alertmanager
        data:
          alertmanager.yml: |
{alertmanager_yaml}
        """
    ).strip()

    documents = "\n---\n".join([grafana_cm, alertmanager_cm, prometheus_rules])
    return documents + "\n"


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Aplicando dashboards e alertas opinativos...")

    namespace = typer.prompt("Namespace de observabilidade", default="observability")
    contact_email = typer.prompt(
        "Email para receber alertas (ENTER para ignorar)",
        default="",
    )
    webhook_url = typer.prompt(
        "Webhook HTTP (Slack/Teams) para Alertmanager (ENTER para ignorar)",
        default="",
    )

    kubectl_create_ns(namespace, ctx)

    manifest = _build_manifest(namespace, contact_email, webhook_url)
    write_file(MANIFEST_PATH, manifest, ctx)
    kubectl_apply(str(MANIFEST_PATH), ctx)

    typer.secho("Dashboards e alertas aplicados no namespace de observabilidade.", fg=typer.colors.GREEN)
    typer.echo("Grafana: ConfigMap 'grafana-dashboards-raijin'")
    typer.echo("Alertmanager: ConfigMap 'alertmanager-raijin'")
    typer.echo("Prometheus: PrometheusRule 'raijin-default-alerts'")
