"""Configuracao do Prometheus Stack via Helm (robust, production-ready)."""

from __future__ import annotations

import json
import socket
import tempfile
import textwrap
import time
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    helm_upgrade_install,
    kubectl_create_ns,
    require_root,
    run_cmd,
)

DEFAULT_NAMESPACE = "observability"
LOCAL_PATH_PROVISIONER_URL = (
    "https://raw.githubusercontent.com/rancher/local-path-provisioner/"
    "v0.0.30/deploy/local-path-storage.yaml"
)


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
    """Retorna o nome da StorageClass default do cluster, se existir."""
    if ctx.dry_run:
        return ""
    result = run_cmd(
        [
            "kubectl",
            "get",
            "storageclass",
            "-o",
            "jsonpath={.items[?(@.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class=='true')].metadata.name}",
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        return (result.stdout or "").strip()
    return ""


def _list_storage_classes(ctx: ExecutionContext) -> list:
    """Lista todas as StorageClasses disponiveis."""
    result = run_cmd(
        ["kubectl", "get", "storageclass", "-o", "jsonpath={.items[*].metadata.name}"],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        return (result.stdout or "").strip().split()
    return []


def _apply_manifest(ctx: ExecutionContext, manifest: str, description: str) -> bool:
    """Aplica manifest YAML temporario com kubectl."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            tmp.write(manifest)
            tmp.flush()
            tmp_path = Path(tmp.name)
        result = run_cmd(
            ["kubectl", "apply", "-f", str(tmp_path)],
            ctx,
            check=False,
        )
        if result.returncode != 0:
            typer.secho(f"  Falha ao aplicar {description}.", fg=typer.colors.RED)
            return False
        typer.secho(f"  ✓ {description} aplicado.", fg=typer.colors.GREEN)
        return True
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _patch_local_path_provisioner_tolerations(ctx: ExecutionContext) -> None:
    """Adiciona tolerations ao local-path-provisioner para rodar em control-plane."""
    typer.echo("  Configurando tolerations no local-path-provisioner...")
    
    # Patch no deployment para tolerar control-plane
    patch_deployment = textwrap.dedent(
        """
        spec:
          template:
            spec:
              tolerations:
              - key: node-role.kubernetes.io/control-plane
                operator: Exists
                effect: NoSchedule
              - key: node-role.kubernetes.io/master
                operator: Exists
                effect: NoSchedule
        """
    ).strip()
    
    result = run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "patch", "deployment",
            "local-path-provisioner", "--patch", patch_deployment,
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        typer.secho("    ✓ Deployment patched com tolerations.", fg=typer.colors.GREEN)
    
    # Patch no ConfigMap para os helper pods (que criam os dirs no node)
    # O local-path-provisioner usa um ConfigMap com helperPod template
    helper_pod_config = {
        "nodePathMap": [
            {
                "node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
                "paths": ["/opt/local-path-provisioner"]
            }
        ],
        "setupCommand": None,
        "teardownCommand": None,
        "helperPod": {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {},
            "spec": {
                "tolerations": [
                    {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node-role.kubernetes.io/master", "operator": "Exists", "effect": "NoSchedule"}
                ],
                "containers": [
                    {
                        "name": "helper-pod",
                        "image": "busybox:stable",
                        "imagePullPolicy": "IfNotPresent"
                    }
                ]
            }
        }
    }
    
    # Converte para JSON string para o patch
    config_json_str = json.dumps(helper_pod_config)
    patch_data = json.dumps({"data": {"config.json": config_json_str}})
    
    # Aplica via patch no ConfigMap
    result = run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "patch", "configmap",
            "local-path-config", "--type=merge", "-p", patch_data,
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        typer.secho("    ✓ ConfigMap patched para helper pods.", fg=typer.colors.GREEN)
    
    # Reinicia o deployment para aplicar as mudanças
    run_cmd(
        ["kubectl", "-n", "local-path-storage", "rollout", "restart", "deployment/local-path-provisioner"],
        ctx,
        check=False,
    )
    
    # Aguarda rollout
    run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "rollout", "status",
            "deployment/local-path-provisioner", "--timeout=60s",
        ],
        ctx,
        check=False,
    )


def _install_local_path_provisioner(ctx: ExecutionContext) -> bool:
    """Instala local-path-provisioner para usar storage local (NVMe/SSD)."""
    typer.echo("Instalando local-path-provisioner para storage local...")
    
    result = run_cmd(
        ["kubectl", "apply", "-f", LOCAL_PATH_PROVISIONER_URL],
        ctx,
        check=False,
    )
    if result.returncode != 0:
        typer.secho("  Falha ao instalar local-path-provisioner.", fg=typer.colors.RED)
        return False
    
    # Aguarda deployment ficar pronto inicialmente
    typer.echo("  Aguardando local-path-provisioner ficar Ready...")
    run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "rollout", "status",
            "deployment/local-path-provisioner", "--timeout=60s",
        ],
        ctx,
        check=False,
    )
    
    # Aplica tolerations para control-plane (single-node clusters)
    _patch_local_path_provisioner_tolerations(ctx)
    
    typer.secho("  ✓ local-path-provisioner instalado e configurado.", fg=typer.colors.GREEN)
    return True


def _set_default_storage_class(ctx: ExecutionContext, name: str) -> None:
    """Define uma StorageClass como default."""
    # Remove default de outras classes primeiro
    existing = _list_storage_classes(ctx)
    for sc in existing:
        if sc != name:
            run_cmd(
                [
                    "kubectl", "annotate", "storageclass", sc,
                    "storageclass.kubernetes.io/is-default-class-",
                    "--overwrite",
                ],
                ctx,
                check=False,
            )
    
    # Define a nova como default
    run_cmd(
        [
            "kubectl", "annotate", "storageclass", name,
            "storageclass.kubernetes.io/is-default-class=true",
            "--overwrite",
        ],
        ctx,
        check=True,
    )
    typer.secho(f"  ✓ StorageClass '{name}' definida como default.", fg=typer.colors.GREEN)


def _ensure_storage_class(ctx: ExecutionContext) -> str:
    """Garante que existe uma StorageClass disponivel, instalando local-path se necessario."""
    if ctx.dry_run:
        return "local-path"  # Retorna um valor dummy para dry-run
    
    default_sc = _get_default_storage_class(ctx)
    available = _list_storage_classes(ctx)

    # Se ja existir default (qualquer uma), usa ela
    if default_sc:
        typer.echo(f"StorageClass default detectada: {default_sc}")
        # Se for local-path, garante que o provisioner tem tolerations
        if default_sc == "local-path" or "local-path" in available:
            _patch_local_path_provisioner_tolerations(ctx)
        return default_sc

    # Se local-path estiver disponivel mas nao for default, define como default
    if "local-path" in available:
        typer.echo("StorageClass 'local-path' detectada.")
        _patch_local_path_provisioner_tolerations(ctx)
        _set_default_storage_class(ctx, "local-path")
        return "local-path"

    # Se houver outras classes disponiveis, pergunta qual usar
    if available:
        typer.echo(f"StorageClasses disponiveis (sem default): {', '.join(available)}")
        choice = typer.prompt(
            f"Qual StorageClass usar? ({'/'.join(available)})",
            default=available[0],
        )
        return choice

    # Nenhuma StorageClass disponivel - instala local-path automaticamente
    typer.secho(
        "Nenhuma StorageClass encontrada no cluster.",
        fg=typer.colors.YELLOW,
    )
    install = typer.confirm(
        "Instalar local-path-provisioner para usar armazenamento local (NVMe/SSD)?",
        default=True,
    )
    if not install:
        typer.secho(
            "Abortando: Prometheus com PVC requer uma StorageClass.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    if not _install_local_path_provisioner(ctx):
        raise typer.Exit(1)

    _set_default_storage_class(ctx, "local-path")
    return "local-path"


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

    # Verifica se existe StorageClass default para sugerir no prompt
    default_sc = _get_default_storage_class(ctx)
    
    enable_persistence = typer.confirm(
        "Habilitar PVC para Prometheus e Alertmanager?", default=bool(default_sc)
    )

    # Se habilitou PVC, garante que existe StorageClass disponivel
    if enable_persistence:
        default_sc = _ensure_storage_class(ctx)

    node_name = _detect_node_name(ctx)

    values = [
        "grafana.enabled=false",
        "prometheus.prometheusSpec.retention=15d",
        "prometheus.prometheusSpec.enableAdminAPI=true",
        "prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false",
        "prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false",
        "defaultRules.create=true",
        # Tolerations for control-plane nodes - Prometheus
        "prometheus.prometheusSpec.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheus.prometheusSpec.tolerations[0].operator=Exists",
        "prometheus.prometheusSpec.tolerations[0].effect=NoSchedule",
        "prometheus.prometheusSpec.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheus.prometheusSpec.tolerations[1].operator=Exists",
        "prometheus.prometheusSpec.tolerations[1].effect=NoSchedule",
        # Tolerations - Alertmanager
        "alertmanager.alertmanagerSpec.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "alertmanager.alertmanagerSpec.tolerations[0].operator=Exists",
        "alertmanager.alertmanagerSpec.tolerations[0].effect=NoSchedule",
        "alertmanager.alertmanagerSpec.tolerations[1].key=node-role.kubernetes.io/master",
        "alertmanager.alertmanagerSpec.tolerations[1].operator=Exists",
        "alertmanager.alertmanagerSpec.tolerations[1].effect=NoSchedule",
        # Tolerations - Prometheus Operator
        "prometheusOperator.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheusOperator.tolerations[0].operator=Exists",
        "prometheusOperator.tolerations[0].effect=NoSchedule",
        "prometheusOperator.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheusOperator.tolerations[1].operator=Exists",
        "prometheusOperator.tolerations[1].effect=NoSchedule",
        # Tolerations - Admission Webhooks (Jobs que criam/atualizam webhooks)
        "prometheusOperator.admissionWebhooks.patch.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "prometheusOperator.admissionWebhooks.patch.tolerations[0].operator=Exists",
        "prometheusOperator.admissionWebhooks.patch.tolerations[0].effect=NoSchedule",
        "prometheusOperator.admissionWebhooks.patch.tolerations[1].key=node-role.kubernetes.io/master",
        "prometheusOperator.admissionWebhooks.patch.tolerations[1].operator=Exists",
        "prometheusOperator.admissionWebhooks.patch.tolerations[1].effect=NoSchedule",
        # Tolerations - kube-state-metrics
        "kube-state-metrics.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "kube-state-metrics.tolerations[0].operator=Exists",
        "kube-state-metrics.tolerations[0].effect=NoSchedule",
        "kube-state-metrics.tolerations[1].key=node-role.kubernetes.io/master",
        "kube-state-metrics.tolerations[1].operator=Exists",
        "kube-state-metrics.tolerations[1].effect=NoSchedule",
        # Tolerations - node-exporter
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

    extra_args = ["--wait", "--timeout", "10m", "--atomic"]

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
