"""Instalacao automatica de ferramentas necessarias para o raijin-server."""

import shutil
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, apt_install, apt_update, require_root, run_cmd, write_file


# Versoes das ferramentas
HELM_VERSION = "3.14.0"
KUBECTL_VERSION = "1.30.0"
ISTIOCTL_VERSION = "1.21.0"
VELERO_VERSION = "1.13.0"


def _install_helm(ctx: ExecutionContext) -> None:
    """Instala Helm via script oficial."""
    if shutil.which("helm") and not ctx.dry_run:
        typer.echo("Helm ja instalado, pulando...")
        return

    typer.echo(f"Instalando Helm v{HELM_VERSION}...")
    run_cmd(
        "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash",
        ctx,
        use_shell=True,
    )


def _install_kubectl(ctx: ExecutionContext) -> None:
    """Instala kubectl via binary."""
    if shutil.which("kubectl") and not ctx.dry_run:
        typer.echo("kubectl ja instalado, pulando...")
        return

    typer.echo(f"Instalando kubectl v{KUBECTL_VERSION}...")
    run_cmd(
        [
            "curl",
            "-fsSL",
            "-o",
            "/tmp/kubectl",
            f"https://dl.k8s.io/release/v{KUBECTL_VERSION}/bin/linux/amd64/kubectl",
        ],
        ctx,
    )
    run_cmd(["chmod", "+x", "/tmp/kubectl"], ctx)
    run_cmd(["mv", "/tmp/kubectl", "/usr/local/bin/kubectl"], ctx)


def _install_istioctl(ctx: ExecutionContext) -> None:
    """Instala istioctl."""
    if shutil.which("istioctl") and not ctx.dry_run:
        typer.echo("istioctl ja instalado, pulando...")
        return

    typer.echo(f"Instalando istioctl v{ISTIOCTL_VERSION}...")
    run_cmd(
        f"curl -L https://istio.io/downloadIstio | ISTIO_VERSION={ISTIOCTL_VERSION} sh -",
        ctx,
        use_shell=True,
        cwd="/tmp",
    )
    run_cmd(
        ["mv", f"/tmp/istio-{ISTIOCTL_VERSION}/bin/istioctl", "/usr/local/bin/istioctl"],
        ctx,
    )
    run_cmd(["chmod", "+x", "/usr/local/bin/istioctl"], ctx)


def _install_velero(ctx: ExecutionContext) -> None:
    """Instala Velero CLI."""
    if shutil.which("velero") and not ctx.dry_run:
        typer.echo("Velero CLI ja instalado, pulando...")
        return

    typer.echo(f"Instalando Velero CLI v{VELERO_VERSION}...")
    tarball = f"velero-v{VELERO_VERSION}-linux-amd64.tar.gz"
    url = f"https://github.com/vmware-tanzu/velero/releases/download/v{VELERO_VERSION}/{tarball}"

    run_cmd(["curl", "-fsSL", "-o", f"/tmp/{tarball}", url], ctx)
    run_cmd(["tar", "-xzf", f"/tmp/{tarball}", "-C", "/tmp"], ctx)
    run_cmd(
        ["mv", f"/tmp/velero-v{VELERO_VERSION}-linux-amd64/velero", "/usr/local/bin/velero"],
        ctx,
    )
    run_cmd(["chmod", "+x", "/usr/local/bin/velero"], ctx)


def _install_containerd(ctx: ExecutionContext) -> None:
    """Configura containerd como container runtime."""
    typer.echo("Configurando containerd...")

    # Carrega modulos do kernel necessarios
    modules_conf = """overlay
br_netfilter
"""
    write_file(Path("/etc/modules-load.d/k8s.conf"), modules_conf, ctx)

    run_cmd(["modprobe", "overlay"], ctx, check=False)
    run_cmd(["modprobe", "br_netfilter"], ctx, check=False)

    # Sysctl para Kubernetes
    sysctl_conf = """net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
"""
    write_file(Path("/etc/sysctl.d/k8s.conf"), sysctl_conf, ctx)
    run_cmd(["sysctl", "--system"], ctx, check=False)

    apt_install(["containerd"], ctx)

    # Gera config padrao
    run_cmd(["mkdir", "-p", "/etc/containerd"], ctx)
    run_cmd("containerd config default > /etc/containerd/config.toml", ctx, use_shell=True)

    # Habilita SystemdCgroup
    run_cmd(
        "sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml",
        ctx,
        use_shell=True,
    )

    run_cmd(["systemctl", "restart", "containerd"], ctx, check=False)
    run_cmd(["systemctl", "enable", "containerd"], ctx, check=False)


def _setup_swap(ctx: ExecutionContext) -> None:
    """Desabilita swap (requisito do Kubernetes)."""
    typer.echo("Desabilitando swap (requisito Kubernetes)...")
    run_cmd(["swapoff", "-a"], ctx, check=False)
    # Remove swap do fstab
    run_cmd(
        "sed -i '/swap/d' /etc/fstab",
        ctx,
        use_shell=True,
        check=False,
    )


def _install_cert_manager(ctx: ExecutionContext) -> None:
    """Instala cert-manager para gerenciamento de certificados TLS."""
    typer.echo("Instalando cert-manager...")
    run_cmd(
        [
            "kubectl",
            "apply",
            "-f",
            "https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml",
        ],
        ctx,
    )


def run(ctx: ExecutionContext) -> None:
    """Instala todas as ferramentas necessarias para o ambiente produtivo."""
    require_root(ctx)

    typer.secho("\n=== Bootstrap: Instalando Ferramentas ===", fg=typer.colors.CYAN, bold=True)

    # Atualiza sistema
    typer.echo("\n[1/8] Atualizando sistema...")
    apt_update(ctx)

    # Pacotes base
    typer.echo("\n[2/8] Instalando pacotes essenciais...")
    apt_install(
        [
            "curl",
            "wget",
            "git",
            "gnupg",
            "lsb-release",
            "ca-certificates",
            "apt-transport-https",
            "software-properties-common",
            "htop",
            "net-tools",
            "vim",
            "jq",
            "unzip",
            "nfs-common",  # Para storage NFS
            "open-iscsi",  # Para iSCSI storage
        ],
        ctx,
    )

    # Desabilita swap
    typer.echo("\n[3/8] Configurando sistema para Kubernetes...")
    _setup_swap(ctx)

    # Containerd
    typer.echo("\n[4/8] Configurando container runtime...")
    _install_containerd(ctx)

    # Helm
    typer.echo("\n[5/8] Instalando Helm...")
    _install_helm(ctx)

    # kubectl
    typer.echo("\n[6/8] Instalando kubectl...")
    _install_kubectl(ctx)

    # istioctl
    typer.echo("\n[7/8] Instalando istioctl...")
    _install_istioctl(ctx)

    # velero
    typer.echo("\n[8/8] Instalando Velero CLI...")
    _install_velero(ctx)

    typer.secho("\n✓ Bootstrap concluido! Ferramentas instaladas.", fg=typer.colors.GREEN, bold=True)

    # Resumo
    typer.echo("\nFerramentas instaladas:")
    tools = ["helm", "kubectl", "istioctl", "velero", "containerd"]
    for tool in tools:
        path = shutil.which(tool)
        if path or ctx.dry_run:
            typer.secho(f"  ✓ {tool}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ {tool} (nao encontrado)", fg=typer.colors.YELLOW)
