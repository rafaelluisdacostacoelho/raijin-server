"""Configuracao do Prometheus Stack via Helm (robust, production-ready)."""

from __future__ import annotations

import typer

from raijin_server.utils import (
    ExecutionContext,
    helm_upgrade_install,
    kubectl_create_ns,
    require_root,
    run_cmd,
)

DEFAULT_NAMESPACE = "observability"


def _get_default_storage_class(ctx: ExecutionContext) -> str:
    if ctx.dry_run:
        return ""
    result = run_cmd(
        [
            "kubectl",
            "get",
            "storageclass",
            "-o",
            "jsonpath={.items[?(@.metadata.annotations['storageclass.kubernetes.io/is-default-class']=='true')].metadata.name}",
        ],
        ctx,
        check=False,
    )
    return (result.stdout or "").strip()


def _ensure_cluster_access(ctx: ExecutionContext) -> None:
    if ctx.dry_run:
        return
    result = run_cmd(["kubectl", "cluster-info"], ctx, check=False)
    if result.returncode != 0:
        typer.secho("Cluster Kubernetes nao acessivel. Verifique kubeconfig/controle-plane.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    _ensure_cluster_access(ctx)

    typer.echo("Instalando kube-prometheus-stack via Helm...")

    namespace = typer.prompt("Namespace destino", default=DEFAULT_NAMESPACE)
    kubectl_create_ns(namespace, ctx)

    default_sc = _get_default_storage_class(ctx)
    enable_persistence = typer.confirm(
        "Habilitar PVC para Prometheus e Alertmanager?", default=bool(default_sc)
    )

    values = [
        "grafana.enabled=false",
        "prometheus.prometheusSpec.retention=15d",
        "prometheus.prometheusSpec.enableAdminAPI=true",
        "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false",
        "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false",
        "defaultRules.create=true",
    ]

    extra_args = ["--wait", "--timeout", "5m", "--atomic"]

    chart_version = typer.prompt(
        "Versao do chart (vazio para latest)",
        default="",
    ).strip()
    if chart_version:
        extra_args.extend(["--version", chart_version])

    if enable_persistence:
        storage_class = typer.prompt(
            "StorageClass para PVC",
            default=default_sc or "",
        ).strip()
        prom_size = typer.prompt("Tamanho PVC Prometheus", default="20Gi")
        alert_size = typer.prompt("Tamanho PVC Alertmanager", default="10Gi")

        if storage_class:
            values.extend(
                [
                    f"prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName={storage_class}",
                    f"alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.storageClassName={storage_class}",
                ]
            )

        values.extend(
            [
                f"prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage={prom_size}",
                f"alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage={alert_size}",
            ]
        )
    else:
        typer.secho(
            "PVC desativado: Prometheus/Alertmanager usarao volumes efemeros (sem retenção apos restart).",
            fg=typer.colors.YELLOW,
        )

    helm_upgrade_install(
        release="kube-prometheus-stack",
        chart="kube-prometheus-stack",
        namespace=namespace,
        repo="prometheus-community",
        repo_url="https://prometheus-community.github.io/helm-charts",
        ctx=ctx,
        values=values,
        extra_args=extra_args,
    )

    typer.secho("kube-prometheus-stack instalado com sucesso.", fg=typer.colors.GREEN)
