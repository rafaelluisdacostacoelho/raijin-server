"""Configuracao do Prometheus Stack via Helm (robust, production-ready)."""

from __future__ import annotations

import socket
import time

import typer

from raijin_server.utils import (
    ExecutionContext,
    helm_upgrade_install,
    kubectl_create_ns,
    require_root,
    run_cmd,
)

DEFAULT_NAMESPACE = "observability"


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


def _check_existing_prometheus(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica se existe instalacao do Prometheus Stack."""
    result = run_cmd(
        ["helm", "status", "kube-prometheus-stack", "-n", namespace],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_prometheus(ctx: ExecutionContext, namespace: str) -> None:
    """Remove instalacao anterior do Prometheus Stack."""
    typer.echo("Removendo instalacao anterior do kube-prometheus-stack...")
    
    run_cmd(
        ["helm", "uninstall", "kube-prometheus-stack", "-n", namespace],
        ctx,
        check=False,
    )
    
    # Remove CRDs if requested
    remove_crds = typer.confirm("Remover CRDs do Prometheus (pode afetar outros operadores)?", default=False)
    if remove_crds:
        crds = [
            "alertmanagerconfigs.monitoring.coreos.com",
            "alertmanagers.monitoring.coreos.com",
            "podmonitors.monitoring.coreos.com",
            "probes.monitoring.coreos.com",
            "prometheusagents.monitoring.coreos.com",
            "prometheuses.monitoring.coreos.com",
            "prometheusrules.monitoring.coreos.com",
            "scrapeconfigs.monitoring.coreos.com",
            "servicemonitors.monitoring.coreos.com",
            "thanosrulers.monitoring.coreos.com",
        ]
        for crd in crds:
            run_cmd(["kubectl", "delete", "crd", crd], ctx, check=False)
    
    remove_data = typer.confirm("Remover PVCs (dados persistentes)?", default=False)
    if remove_data:
        run_cmd(
            ["kubectl", "-n", namespace, "delete", "pvc", "-l", "app.kubernetes.io/name=prometheus"],
            ctx,
            check=False,
        )
        run_cmd(
            ["kubectl", "-n", namespace, "delete", "pvc", "-l", "app.kubernetes.io/name=alertmanager"],
            ctx,
            check=False,
        )
    
    time.sleep(5)


def _wait_for_prometheus_ready(ctx: ExecutionContext, namespace: str, timeout: int = 300) -> bool:
    """Aguarda pods do Prometheus Stack ficarem Ready."""
    typer.echo("Aguardando pods do Prometheus Stack ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
                "-l", "app.kubernetes.io/instance=kube-prometheus-stack",
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
                    typer.secho("  Prometheus Stack Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Prometheus Stack.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    _ensure_cluster_access(ctx)

    typer.echo("Instalando kube-prometheus-stack via Helm...")

    namespace = typer.prompt("Namespace destino", default=DEFAULT_NAMESPACE)

    # Prompt opcional de limpeza
    if _check_existing_prometheus(ctx, namespace):
        cleanup = typer.confirm(
            "Instalacao anterior do Prometheus Stack detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_prometheus(ctx, namespace)

    kubectl_create_ns(namespace, ctx)

    default_sc = _get_default_storage_class(ctx)
    enable_persistence = typer.confirm(
        "Habilitar PVC para Prometheus e Alertmanager?", default=bool(default_sc)
    )

    node_name = _detect_node_name(ctx)

    values = [
        "grafana.enabled=false",
        "prometheus.prometheusSpec.retention=15d",
        "prometheus.prometheusSpec.enableAdminAPI=true",
        "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false",
        "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false",
        "defaultRules.create=true",
        # Tolerations for control-plane nodes
        "prometheus.prometheusSpec.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheus.prometheusSpec.tolerations[0].operator=Exists",
        "prometheus.prometheusSpec.tolerations[0].effect=NoSchedule",
        "prometheus.prometheusSpec.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheus.prometheusSpec.tolerations[1].operator=Exists",
        "prometheus.prometheusSpec.tolerations[1].effect=NoSchedule",
        "alertmanager.alertmanagerSpec.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "alertmanager.alertmanagerSpec.tolerations[0].operator=Exists",
        "alertmanager.alertmanagerSpec.tolerations[0].effect=NoSchedule",
        "alertmanager.alertmanagerSpec.tolerations[1].key=node-role.kubernetes.io/master",
        "alertmanager.alertmanagerSpec.tolerations[1].operator=Exists",
        "alertmanager.alertmanagerSpec.tolerations[1].effect=NoSchedule",
        "prometheusOperator.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheusOperator.tolerations[0].operator=Exists",
        "prometheusOperator.tolerations[0].effect=NoSchedule",
        "prometheusOperator.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheusOperator.tolerations[1].operator=Exists",
        "prometheusOperator.tolerations[1].effect=NoSchedule",
        "kube-state-metrics.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "kube-state-metrics.tolerations[0].operator=Exists",
        "kube-state-metrics.tolerations[0].effect=NoSchedule",
        "kube-state-metrics.tolerations[1].key=node-role.kubernetes.io/master",
        "kube-state-metrics.tolerations[1].operator=Exists",
        "kube-state-metrics.tolerations[1].effect=NoSchedule",
        "prometheus-node-exporter.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheus-node-exporter.tolerations[0].operator=Exists",
        "prometheus-node-exporter.tolerations[0].effect=NoSchedule",
        "prometheus-node-exporter.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheus-node-exporter.tolerations[1].operator=Exists",
        "prometheus-node-exporter.tolerations[1].effect=NoSchedule",
        # NodeSelector
        f"prometheus.prometheusSpec.nodeSelector.kubernetes\\.io/hostname={node_name}",
        f"alertmanager.alertmanagerSpec.nodeSelector.kubernetes\\.io/hostname={node_name}",
        f"prometheusOperator.nodeSelector.kubernetes\\.io/hostname={node_name}",
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

    if not ctx.dry_run:
        _wait_for_prometheus_ready(ctx, namespace)

    typer.secho("\n✓ kube-prometheus-stack instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nPara acessar Prometheus via port-forward:")
    typer.echo(f"  kubectl -n {namespace} port-forward svc/kube-prometheus-stack-prometheus 9090:9090")
    typer.echo("\nPara acessar Alertmanager via port-forward:")
    typer.echo(f"  kubectl -n {namespace} port-forward svc/kube-prometheus-stack-alertmanager 9093:9093")
