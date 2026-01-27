"""Configuracao de Calico como CNI com CIDR customizado e policy default-deny."""

from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, kubectl_apply, require_root, run_cmd, write_file


def run(ctx: ExecutionContext) -> None:
        require_root(ctx)
        ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
        ensure_tool("curl", ctx, install_hint="Instale curl.")

        typer.echo("Aplicando Calico como CNI...")
        pod_cidr = typer.prompt("Pod CIDR (Calico)", default="10.244.0.0/16")

        manifest_url = "https://raw.githubusercontent.com/projectcalico/calico/v3.27.2/manifests/calico.yaml"
        cmd = f"curl -s {manifest_url} | sed 's#192.168.0.0/16#{pod_cidr}#' | kubectl apply -f -"
        run_cmd(cmd, ctx, use_shell=True)

        # NetworkPolicy default-deny para workloads (excepto kube-system).
        default_deny = """apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
    name: default-deny-all
    namespace: default
spec:
    podSelector: {}
    policyTypes:
    - Ingress
    - Egress
"""
        policy_path = Path("/tmp/raijin-default-deny.yaml")
        write_file(policy_path, default_deny, ctx)
        kubectl_apply(str(policy_path), ctx)
