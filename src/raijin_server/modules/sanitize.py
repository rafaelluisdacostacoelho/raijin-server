"""Sanitizacao do servidor antes de nova instalacao Kubernetes."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, require_root, run_cmd

SYSTEMD_SERVICES = [
    "kubelet",
    "containerd",
]

APT_PACKAGES = [
    "kubeadm",
    "kubelet",
    "kubectl",
    "kubernetes-cni",
    "cri-tools",
    "containerd",
]

CLEAN_PATHS = [
    "/etc/kubernetes",
    "/etc/cni/net.d",
    "/etc/calico",
    "/var/lib/etcd",
    "/var/lib/kubelet",
    "/var/lib/cni",
    "/var/lib/containerd",
    "/var/run/kubernetes",
    "/var/lib/dockershim",
]

TOOL_BINARIES = [
    "/usr/local/bin/kubectl",
    "/usr/local/bin/helm",
    "/usr/local/bin/istioctl",
    "/usr/local/bin/velero",
]

APT_MARKERS = [
    "/etc/apt/sources.list.d/kubernetes.list",
    "/etc/apt/keyrings/kubernetes-apt-keyring.gpg",
]


def _stop_services(ctx: ExecutionContext) -> None:
    typer.echo("Parando serviços relacionados (kubelet, containerd)...")
    for service in SYSTEMD_SERVICES:
        run_cmd(["systemctl", "stop", service], ctx, check=False)
        run_cmd(["systemctl", "disable", service], ctx, check=False)


def _kubeadm_reset(ctx: ExecutionContext) -> None:
    typer.echo("Executando kubeadm reset...")
    if shutil.which("kubeadm") or ctx.dry_run:
        run_cmd(["kubeadm", "reset", "-f"], ctx, check=False)
    else:
        typer.echo("kubeadm nao encontrado, pulando reset.")


def _flush_iptables(ctx: ExecutionContext) -> None:
    typer.echo("Limpando regras iptables/ip6tables e IPVS...")
    tables = ["filter", "nat", "mangle", "raw"]
    if shutil.which("iptables") or ctx.dry_run:
        for table in tables:
            run_cmd(["iptables", "-t", table, "-F"], ctx, check=False)
            run_cmd(["iptables", "-t", table, "-X"], ctx, check=False)
    if shutil.which("ip6tables") or ctx.dry_run:
        for table in tables:
            run_cmd(["ip6tables", "-t", table, "-F"], ctx, check=False)
            run_cmd(["ip6tables", "-t", table, "-X"], ctx, check=False)
    if shutil.which("ipvsadm") or ctx.dry_run:
        run_cmd(["ipvsadm", "--clear"], ctx, check=False)


def _purge_packages(ctx: ExecutionContext) -> None:
    typer.echo("Removendo pacotes kube* e containerd...")
    run_cmd(["apt-get", "purge", "-y", *APT_PACKAGES], ctx, check=False)
    run_cmd(["apt-get", "autoremove", "-y"], ctx, check=False)
    run_cmd(["apt-get", "clean"], ctx, check=False)


def _remove_paths(ctx: ExecutionContext) -> None:
    typer.echo("Removendo arquivos e diretorios residuais...")
    for path in CLEAN_PATHS:
        run_cmd(["rm", "-rf", path], ctx, check=False)
    # Remove kubeconfigs de root e usuarios em /home
    run_cmd(["rm", "-rf", "/root/.kube"], ctx, check=False)
    home = Path("/home")
    if home.exists() and home.is_dir():
        for entry in home.iterdir():
            candidate = entry / ".kube"
            run_cmd(["rm", "-rf", str(candidate)], ctx, check=False)


def _remove_tool_binaries(ctx: ExecutionContext) -> None:
    typer.echo("Removendo binarios antigos (kubectl, helm, istioctl, velero)...")
    for binary in TOOL_BINARIES:
        run_cmd(["rm", "-f", binary], ctx, check=False)


def _remove_apt_markers(ctx: ExecutionContext) -> None:
    typer.echo("Limpando lista e chave do repositório Kubernetes...")
    for marker in APT_MARKERS:
        run_cmd(["rm", "-f", marker], ctx, check=False)


def run(ctx: ExecutionContext) -> None:
    """Remove instalacoes antigas de Kubernetes antes de reinstalar."""
    require_root(ctx)

    typer.secho("\n=== Sanitizacao do ambiente Kubernetes ===", fg=typer.colors.CYAN, bold=True)
    typer.echo(
        "Este passo remove clusters existentes, pacotes kube* e arquivos residuais."
        " Use apenas em servidores dedicados ao Raijin Server."
    )

    if ctx.dry_run:
        typer.echo("[dry-run] Confirmacao automatica para demonstracao.")
    else:
        proceed = typer.confirm(
            "Deseja realmente limpar o servidor antes de uma nova instalacao?",
            default=False,
        )
        if not proceed:
            typer.echo("Sanitizacao cancelada pelo usuario.")
            return

    _stop_services(ctx)
    _kubeadm_reset(ctx)
    _flush_iptables(ctx)
    _purge_packages(ctx)
    _remove_paths(ctx)
    _remove_tool_binaries(ctx)
    _remove_apt_markers(ctx)

    typer.secho("\n✓ Sanitizacao concluida. Servidor pronto para novo full_install.", fg=typer.colors.GREEN, bold=True)
