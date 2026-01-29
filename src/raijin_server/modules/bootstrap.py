"""Instalacao automatica de ferramentas necessarias para o raijin-server."""

import shutil
import platform
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, apt_install, apt_update, require_root, run_cmd, write_file


def _kernel_headers_present() -> bool:
    """Verifica se os headers do kernel atual estao presentes."""

    release = platform.uname().release
    return Path(f"/lib/modules/{release}/build").exists()


def _ensure_kernel_headers(ctx: ExecutionContext) -> None:
    """Instala headers do kernel se ausentes; falha de forma clara se nao encontrar."""

    if _kernel_headers_present():
        return

    release = platform.uname().release
    header_pkg = f"linux-headers-{release}"
    typer.secho(
        f"Headers do kernel {release} nao encontrados. Instalando {header_pkg}...",
        fg=typer.colors.YELLOW,
    )
    apt_install([header_pkg], ctx)

    if not _kernel_headers_present():
        typer.secho(
            f"Headers ainda ausentes apos instalar {header_pkg}. Verifique repos ou kernel custom.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


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
    
    # Limpa tentativas anteriores
    istio_dir = Path(f"/tmp/istio-{ISTIOCTL_VERSION}")
    if istio_dir.exists() and not ctx.dry_run:
        run_cmd(["rm", "-rf", str(istio_dir)], ctx, check=False)
    
    # Download do Istio
    run_cmd(
        f"curl -L https://istio.io/downloadIstio | ISTIO_VERSION={ISTIOCTL_VERSION} sh -",
        ctx,
        use_shell=True,
        cwd="/tmp",
    )
    
    # Verifica se o download foi bem sucedido
    istioctl_path = Path(f"/tmp/istio-{ISTIOCTL_VERSION}/bin/istioctl")
    if not ctx.dry_run and not istioctl_path.exists():
        typer.secho(
            f"Falha ao baixar istioctl. Arquivo nao encontrado: {istioctl_path}",
            fg=typer.colors.RED,
        )
        typer.secho("Verifique sua conexao de internet e tente novamente.", fg=typer.colors.YELLOW)
        ctx.warnings.append("istioctl nao instalado - download falhou")
        return  # Nao falha o modulo inteiro, apenas avisa
    
    run_cmd(
        ["mv", str(istioctl_path), "/usr/local/bin/istioctl"],
        ctx,
    )
    run_cmd(["chmod", "+x", "/usr/local/bin/istioctl"], ctx)
    typer.secho("✓ istioctl instalado com sucesso.", fg=typer.colors.GREEN)


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

    _ensure_kernel_headers(ctx)

    # Carrega modulos do kernel necessarios
    modules_conf = """overlay
br_netfilter
"""
    write_file(Path("/etc/modules-load.d/k8s.conf"), modules_conf, ctx)

    run_cmd(["modprobe", "overlay"], ctx, check=False)
    run_cmd(["modprobe", "br_netfilter"], ctx, check=False)

    if not Path("/proc/sys/net/bridge/bridge-nf-call-iptables").exists():
        typer.secho(
            "Arquivo /proc/sys/net/bridge/bridge-nf-call-iptables ausente. Verifique suporte a br_netfilter no kernel.",
            fg=typer.colors.YELLOW,
        )

    # Sysctl para Kubernetes
    sysctl_conf = """net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
"""
    write_file(Path("/etc/sysctl.d/k8s.conf"), sysctl_conf, ctx)
    run_cmd(["sysctl", "--system"], ctx, check=False)

    # Verificacao best-effort dos tunables
    try:
        with open("/proc/sys/net/bridge/bridge-nf-call-iptables") as f:
            val = f.read().strip()
            if val != "1":
                typer.secho(
                    "bridge-nf-call-iptables nao ficou em 1 (cheque modulo br_netfilter e sysctl).",
                    fg=typer.colors.YELLOW,
                )
    except Exception:
        pass

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

    # Precheck Secure Boot (pode afetar modulos DKMS e drivers)
    try:
        sb_path = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
        secure_boot = False
        if sb_path.exists():
            data = sb_path.read_bytes()
            secure_boot = len(data) >= 5 and data[4] == 1
        if secure_boot:
            typer.secho(
                "Secure Boot detectado: modulos DKMS (WireGuard, drivers) podem exigir assinatura.",
                fg=typer.colors.YELLOW,
            )
    except Exception:
        pass

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
