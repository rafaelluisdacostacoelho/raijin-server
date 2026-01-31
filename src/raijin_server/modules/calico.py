"""Configuracao de Calico como CNI com CIDR customizado e policies opinativas."""

import json
from pathlib import Path
from typing import Iterable, List

import typer

from raijin_server.utils import (
    ExecutionContext,
    ensure_tool,
    kubectl_apply,
    require_root,
    run_cmd,
    write_file,
)

EGRESS_LABEL_KEY = "networking.raijin.dev/egress"
EGRESS_LABEL_VALUE = "internet"
DEFAULT_WORKLOAD_NAMESPACE = "apps"


def _apply_policy(content: str, ctx: ExecutionContext, suffix: str) -> None:
    path = Path(f"/tmp/raijin-{suffix}.yaml")
    write_file(path, content, ctx)
    kubectl_apply(str(path), ctx)
    path.unlink(missing_ok=True)


def _ensure_namespace(namespace: str, ctx: ExecutionContext) -> None:
    """Garante que um namespace de workloads exista com labels padrao."""
    manifest = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    raijin/workload-profile: production
    networking.raijin.dev/default-egress: restricted
"""

    path = Path(f"/tmp/raijin-ns-{namespace}.yaml")
    write_file(path, manifest, ctx)
    kubectl_apply(str(path), ctx)
    path.unlink(missing_ok=True)


def _build_default_deny(namespace: str) -> str:
    return f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: {namespace}
spec:
  podSelector: {{}}
  policyTypes:
  - Ingress
  - Egress
"""


def _build_allow_internet(namespace: str, cidr: str) -> str:
    return f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-internet
  namespace: {namespace}
spec:
  podSelector:
    matchLabels:
      {EGRESS_LABEL_KEY}: {EGRESS_LABEL_VALUE}
  policyTypes:
  - Egress
  egress:
  - to:
    - ipBlock:
        cidr: {cidr}
"""


def _split_namespaces(raw_value: str) -> Iterable[str]:
    return [ns.strip() for ns in raw_value.split(",") if ns.strip()]


def _list_workloads_without_egress(namespaces: List[str], ctx: ExecutionContext) -> None:
    """Lista workloads sem label de egress e apenas avisa se falhar."""
    if ctx.dry_run:
        typer.echo("[dry-run] Skip listagem de workloads para liberação de egress")
        return

    typer.secho("\nWorkloads sem liberação de egress (adicione label para liberar internet):", fg=typer.colors.CYAN)
    for ns in namespaces:
        result = run_cmd(
            ["kubectl", "get", "deploy,statefulset,daemonset", "-n", ns, "-o", "json"],
            ctx,
            check=False,
        )
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "erro desconhecido").strip()
            typer.secho(f"  Aviso: nao foi possivel listar workloads em '{ns}' ({msg})", fg=typer.colors.YELLOW)
            continue

        try:
            data = json.loads(result.stdout or "{}")
            items = data.get("items", [])
            pending = []
            for item in items:
                meta = item.get("metadata", {})
                labels = meta.get("labels", {}) or {}
                if labels.get(EGRESS_LABEL_KEY) != EGRESS_LABEL_VALUE:
                    pending.append(f"{meta.get('namespace', ns)}/{meta.get('name', 'desconhecido')}")

            if pending:
                for name in pending:
                    typer.echo(f"  - {name}")
            else:
                typer.echo(f"  Nenhum workload pendente em '{ns}'")
        except Exception as exc:
            typer.secho(f"  Aviso: falha ao processar workloads em '{ns}': {exc}", fg=typer.colors.YELLOW)


def _check_cluster_available(ctx: ExecutionContext) -> bool:
    """Verifica se o cluster Kubernetes esta acessivel."""
    if ctx.dry_run:
        return True
    try:
        result = run_cmd(
            ["kubectl", "cluster-info"],
            ctx,
            check=False,
            retries=1,
        )
        return result.returncode == 0
    except Exception:
        return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    ensure_tool("curl", ctx, install_hint="Instale curl.")

    # Verifica se cluster esta disponivel antes de aplicar
    if not _check_cluster_available(ctx):
        typer.secho(
            "✗ Cluster Kubernetes nao esta acessivel. Execute o modulo 'kubernetes' primeiro.",
            fg=typer.colors.RED,
        )
        typer.secho(
            "  Verifique: kubectl cluster-info",
            fg=typer.colors.YELLOW,
        )
        ctx.errors.append("Calico: cluster nao acessivel")
        raise typer.Exit(code=1)

    typer.echo("Aplicando Calico como CNI...")
    pod_cidr = typer.prompt("Pod CIDR (Calico)", default="10.244.0.0/16")

    typer.secho(
        f"Criando namespace padrao de workloads '{DEFAULT_WORKLOAD_NAMESPACE}' (production-ready)...",
        fg=typer.colors.CYAN,
    )
    _ensure_namespace(DEFAULT_WORKLOAD_NAMESPACE, ctx)

    manifest_url = "https://raw.githubusercontent.com/projectcalico/calico/v3.27.2/manifests/calico.yaml"
    cmd = f"curl -s {manifest_url} | sed 's#192.168.0.0/16#{pod_cidr}#' | kubectl apply -f -"
    run_cmd(cmd, ctx, use_shell=True)

    deny_namespaces_raw = typer.prompt(
        "Namespaces para aplicar default-deny (CSV)",
        default=DEFAULT_WORKLOAD_NAMESPACE,
    )
    for namespace in _split_namespaces(deny_namespaces_raw):
        typer.echo(f"Aplicando default-deny no namespace '{namespace}'...")
        _apply_policy(_build_default_deny(namespace), ctx, f"default-deny-{namespace}")

    if typer.confirm(
        "Deseja liberar saida para internet (pods rotulados) em alguns namespaces?",
        default=True,
    ):
        allow_namespaces_raw = typer.prompt(
            "Namespaces com pods que precisam acessar APIs externas (CSV)",
            default=DEFAULT_WORKLOAD_NAMESPACE,
        )
        cidr = typer.prompt("CIDR liberado (ex.: 0.0.0.0/0)", default="0.0.0.0/0")
        namespaces = list(_split_namespaces(allow_namespaces_raw))
        if namespaces:
            _list_workloads_without_egress(namespaces, ctx)
        for namespace in _split_namespaces(allow_namespaces_raw):
            typer.echo(
                f"Criando policy allow-egress-internet em '{namespace}' para pods com "
                f"label {EGRESS_LABEL_KEY}={EGRESS_LABEL_VALUE}"
            )
            _apply_policy(
                _build_allow_internet(namespace, cidr),
                ctx,
                f"allow-egress-{namespace}",
            )
        typer.echo(
            "Para habilitar egress em um workload específico execute:\n"
            f"  kubectl label deployment MEU-APP -n <namespace> {EGRESS_LABEL_KEY}={EGRESS_LABEL_VALUE}"
        )
