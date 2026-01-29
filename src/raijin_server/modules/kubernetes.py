"""Preparacao de cluster Kubernetes com kubeadm."""

import os
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    apt_install,
    apt_update,
    enable_service,
    ensure_tool,
    require_root,
    run_cmd,
    write_file,
)


def _cleanup_old_repo(ctx: ExecutionContext) -> None:
    """Remove repo legado apt.kubernetes.io se existir para evitar erro 404."""

    repo_file = Path("/etc/apt/sources.list.d/kubernetes.list")
    if ctx.dry_run:
        typer.echo("[dry-run] checando repos antigos em /etc/apt/sources.list.d/kubernetes.list")
        return

    if repo_file.exists():
        try:
            content = repo_file.read_text()
            if "apt.kubernetes.io" in content:
                repo_file.unlink()
                typer.echo("Repo antigo apt.kubernetes.io removido.")
        except Exception:
            typer.echo("Nao foi possivel ler/remover repo antigo apt.kubernetes.io (ok prosseguir).")


def _reset_cluster(ctx: ExecutionContext) -> None:
    """Executa kubeadm reset para limpar instalacao anterior."""
    typer.secho("Limpando instalacao anterior do Kubernetes...", fg=typer.colors.YELLOW)
    run_cmd(["kubeadm", "reset", "-f"], ctx, check=False)
    # Remove configs residuais
    run_cmd(["rm", "-rf", "/etc/kubernetes/manifests", "/etc/kubernetes/pki"], ctx, check=False)
    run_cmd(["rm", "-rf", "/var/lib/etcd"], ctx, check=False)
    run_cmd(["rm", "-rf", "/root/.kube/config"], ctx, check=False)
    # Remove CNI configs
    run_cmd(["rm", "-rf", "/etc/cni/net.d"], ctx, check=False)
    run_cmd(["rm", "-rf", "/var/lib/cni"], ctx, check=False)
    typer.secho("✓ Limpeza concluida.", fg=typer.colors.GREEN)


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando e preparando Kubernetes (kubeadm/kubelet/kubectl)...")

    # Verifica se cluster ja foi inicializado
    kubeconfig_exists = Path("/etc/kubernetes/admin.conf").exists()
    if kubeconfig_exists and not ctx.dry_run:
        typer.secho("⚠ Cluster Kubernetes ja parece estar inicializado.", fg=typer.colors.YELLOW)
        reset_choice = typer.confirm("Deseja limpar e reinstalar? (recomendado)")
        if reset_choice:
            _reset_cluster(ctx)
        elif not typer.confirm("Deseja continuar sem limpar? (pode causar problemas)"):
            typer.echo("Operacao cancelada pelo usuario.")
            return

    _cleanup_old_repo(ctx)
    apt_update(ctx)
    apt_install(
        [
            "apt-transport-https",
            "ca-certificates",
            "curl",
            "gnupg",
            "lsb-release",
            "containerd",
        ],
        ctx,
    )

    # Novo repo oficial (pkgs.k8s.io) substitui apt.kubernetes.io, que nao tem Release em distros recentes.
    repo_version = "v1.30"
    key_url = f"https://pkgs.k8s.io/core:/stable:/{repo_version}/deb/Release.key"
    key_tmp = Path("/tmp/kubernetes-release.key")
    key_path = Path("/etc/apt/keyrings/kubernetes-apt-keyring.gpg")
    repo_entry = f"deb [signed-by={key_path}] https://pkgs.k8s.io/core:/stable:/{repo_version}/deb/ /"

    # Verifica se ja tem a chave instalada
    if not key_path.exists() or ctx.dry_run:
        typer.echo("Baixando chave GPG do Kubernetes (pkgs.k8s.io)...")
        run_cmd(
            [
                "curl",
                "-fsSL",
                "--retry",
                "3",
                "--retry-delay",
                "2",
                "-o",
                str(key_tmp),
                key_url,
            ],
            ctx,
        )

        run_cmd(["mkdir", "-p", "/etc/apt/keyrings"], ctx)

        if not ctx.dry_run:
            if not key_tmp.exists() or key_tmp.stat().st_size == 0:
                typer.secho("Falha ao baixar chave GPG do Kubernetes. Verifique conectividade.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            run_cmd(["gpg", "--yes", "--dearmor", "-o", str(key_path), str(key_tmp)], ctx)
            if not key_path.exists() or key_path.stat().st_size == 0:
                typer.secho("Chave GPG nao foi gravada corretamente.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            key_tmp.unlink(missing_ok=True)
    else:
        typer.echo("Chave GPG do Kubernetes ja existe, pulando download.")

    repo_file = Path("/etc/apt/sources.list.d/kubernetes.list")
    if not repo_file.exists() or ctx.dry_run:
        run_cmd(
            f'echo "{repo_entry}" | tee /etc/apt/sources.list.d/kubernetes.list',
            ctx,
            use_shell=True,
        )

    apt_update(ctx)
    apt_install(["kubelet", "kubeadm", "kubectl"], ctx)

    # Hold das versoes para evitar upgrades automaticos
    run_cmd(["apt-mark", "hold", "kubelet", "kubeadm", "kubectl"], ctx, check=False)

    # Configura containerd com SystemdCgroup.
    run_cmd(["mkdir", "-p", "/etc/containerd"], ctx)
    
    # Verifica se config do containerd ja existe
    containerd_config = Path("/etc/containerd/config.toml")
    if not containerd_config.exists() or ctx.dry_run:
        run_cmd("containerd config default > /etc/containerd/config.toml", ctx, use_shell=True)
    
    # Aplica SystemdCgroup
    run_cmd("sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml", ctx, use_shell=True)
    run_cmd(["systemctl", "restart", "containerd"], ctx, check=False)

    enable_service("containerd", ctx)
    enable_service("kubelet", ctx)

    # kubeadm exige ip_forward=1; sobrepoe ajuste de hardening para fase de cluster.
    # Desabilita IPv6 completamente para evitar erros de preflight e simplificar rede
    sysctl_k8s = """# Kubernetes network settings
net.ipv4.ip_forward=1
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
# Disable IPv6 completely
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv6.conf.lo.disable_ipv6=1
"""
    write_file(Path("/etc/sysctl.d/99-kubernetes.conf"), sysctl_k8s, ctx)
    run_cmd(["sysctl", "--system"], ctx, check=False)

    # Prompts de configuracao
    pod_cidr = typer.prompt("Pod CIDR", default="10.244.0.0/16")
    service_cidr = typer.prompt("Service CIDR", default="10.96.0.0/12")
    cluster_name = typer.prompt("Nome do cluster", default="raijin")
    advertise_address = typer.prompt("API advertise address", default="0.0.0.0")

    kubeadm_config = f"""apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
clusterName: {cluster_name}
kubernetesVersion: stable
controlPlaneEndpoint: {advertise_address}:6443
networking:
  podSubnet: {pod_cidr}
  serviceSubnet: {service_cidr}
apiServer:
  extraArgs:
    authorization-mode: Node,RBAC
  timeoutForControlPlane: 4m0s
controllerManager: {{}}
scheduler: {{}}
---
apiVersion: kubeproxy.config.k8s.io/v1alpha1
kind: KubeProxyConfiguration
mode: ipvs
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
"""

    cfg_path = Path("/etc/kubernetes/kubeadm-config.yaml")
    write_file(cfg_path, kubeadm_config, ctx)

    ensure_tool("kubeadm", ctx, install_hint="Instale kubeadm (apt install kubeadm).")
    run_cmd(["kubeadm", "config", "images", "pull"], ctx, check=False)
    # Ignora erros de preflight relacionados a IPv6 (desabilitado)
    run_cmd(
        [
            "kubeadm", "init",
            "--config", str(cfg_path),
            "--upload-certs",
            "--ignore-preflight-errors=FileContent--proc-sys-net-ipv6-conf-default-forwarding",
        ],
        ctx,
    )

    # Configura kubeconfig para root e sudoer.
    run_cmd(["mkdir", "-p", "/root/.kube"], ctx)
    run_cmd(["cp", "/etc/kubernetes/admin.conf", "/root/.kube/config"], ctx)
    run_cmd("chown $(id -u):$(id -g) /root/.kube/config", ctx, use_shell=True)

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        user_home = Path(f"/home/{sudo_user}")
        kube_dir = user_home / ".kube"
        run_cmd(["mkdir", "-p", str(kube_dir)], ctx)
        run_cmd(["cp", "/etc/kubernetes/admin.conf", str(kube_dir / "config")], ctx)
        run_cmd(["chown", f"{sudo_user}:{sudo_user}", str(kube_dir / "config")], ctx)

    typer.echo("Comando de join para workers:")
    run_cmd(["kubeadm", "token", "create", "--print-join-command"], ctx, check=False)
