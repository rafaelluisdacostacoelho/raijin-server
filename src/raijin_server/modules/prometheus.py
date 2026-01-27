"""Configuracao do Prometheus Stack via Helm."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando kube-prometheus-stack via Helm...")

    values = [
        "grafana.enabled=false",
        "prometheus.prometheusSpec.retention=15d",
        "prometheus.prometheusSpec.enableAdminAPI=true",
        "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false",
        "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=20Gi",
        "alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage=10Gi",
        "defaultRules.create=true",
    ]

    helm_upgrade_install(
        release="kube-prometheus-stack",
        chart="kube-prometheus-stack",
        namespace="observability",
        repo="prometheus-community",
        repo_url="https://prometheus-community.github.io/helm-charts",
        ctx=ctx,
        values=values,
    )
