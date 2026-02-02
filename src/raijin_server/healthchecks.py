"""Health checks para validar estado dos servicos apos instalacao."""

from __future__ import annotations

import subprocess
import time
from typing import Callable, Tuple

import typer

from raijin_server.utils import ExecutionContext, logger

SEALED_NS = "kube-system"
ESO_NS = "external-secrets"
CERT_NS = "cert-manager"


def wait_for_condition(
    check_fn: Callable[[], bool],
    description: str,
    timeout: int = 300,
    interval: int = 10,
) -> bool:
    """Aguarda ate que uma condicao seja satisfeita ou timeout.

    Args:
        check_fn: Funcao que retorna True quando condicao e satisfeita
        description: Descricao da condicao sendo aguardada
        timeout: Tempo maximo de espera em segundos
        interval: Intervalo entre verificacoes em segundos

    Returns:
        True se condicao foi satisfeita, False se timeout
    """
    elapsed = 0
    typer.echo(f"Aguardando: {description}...")

    while elapsed < timeout:
        if check_fn():
            typer.secho(f"✓ {description} [OK]", fg=typer.colors.GREEN)
            return True

        time.sleep(interval)
        elapsed += interval
        typer.echo(f"  ... ainda aguardando ({elapsed}/{timeout}s)")

    typer.secho(f"✗ {description} [TIMEOUT]", fg=typer.colors.RED)
    return False


def check_systemd_service(service: str, ctx: ExecutionContext) -> Tuple[bool, str]:
    """Verifica se um servico systemd esta ativo."""
    if ctx.dry_run:
        return True, "dry-run mode"

    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        if result.returncode == 0 and status == "active":
            return True, "active"
        return False, status
    except Exception as e:
        return False, f"error: {e}"


def check_k8s_node_ready(ctx: ExecutionContext, timeout: int = 300) -> bool:
    """Verifica se o node Kubernetes esta Ready."""
    if ctx.dry_run:
        typer.echo("[dry-run] Pulando verificacao de node Kubernetes")
        return True

    def check():
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.conditions[?(@.type=='Ready')].status}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and "True" in result.stdout
        except Exception:
            return False

    return wait_for_condition(check, "Node Kubernetes Ready", timeout=timeout)


def check_k8s_pods_in_namespace(namespace: str, ctx: ExecutionContext, timeout: int = 300) -> bool:
    """Verifica se todos os pods em um namespace estao Running."""
    if ctx.dry_run:
        typer.echo(f"[dry-run] Pulando verificacao de pods no namespace {namespace}")
        return True

    def check():
        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "pods", "-n", namespace,
                    "-o", "jsonpath={.items[*].status.phase}"
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False

            phases = result.stdout.strip().split()
            if not phases:
                return False

            return all(phase in ["Running", "Succeeded"] for phase in phases)
        except Exception:
            return False

    return wait_for_condition(
        check,
        f"Pods no namespace '{namespace}' Running",
        timeout=timeout
    )


def check_swap_disabled(ctx: ExecutionContext) -> tuple[bool, str]:
    """Confirma que nao ha swap ativa (requisito kubeadm/kubelet)."""
    if ctx.dry_run:
        return True, "dry-run"
    try:
        with open("/proc/swaps") as f:
            lines = f.read().strip().splitlines()
        # /proc/swaps tem header + linhas; se so header, swap esta off
        if len(lines) <= 1:
            return True, "swap desativada"
        return False, "swap ativa (remova entradas do fstab e execute swapoff -a)"
    except Exception as exc:
        return False, f"falha ao verificar swap: {exc}"


def check_helm_release(release: str, namespace: str, ctx: ExecutionContext) -> Tuple[bool, str]:
    """Verifica status de um release Helm."""
    if ctx.dry_run:
        return True, "dry-run mode"

    try:
        result = subprocess.run(
            ["helm", "status", release, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            status = data.get("info", {}).get("status", "unknown")
            return status == "deployed", status
        return False, "not found"
    except Exception as e:
        return False, f"error: {e}"


def check_port_listening(port: int, ctx: ExecutionContext) -> Tuple[bool, str]:
    """Verifica se uma porta esta em listening."""
    if ctx.dry_run:
        return True, "dry-run mode"

    try:
        result = subprocess.run(
            ["ss", "-tuln"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            listening = any(f":{port}" in line for line in result.stdout.split("\n"))
            return listening, "listening" if listening else "not listening"
        return False, "ss command failed"
    except Exception as e:
        return False, f"error: {e}"


def verify_essentials(ctx: ExecutionContext) -> bool:
    """Health check para modulo essentials."""
    logger.info("Verificando health check: essentials")
    typer.secho("\n=== Health Check: Essentials ===", fg=typer.colors.CYAN)

    checks = [
        ("timedatectl NTP", lambda: subprocess.run(["timedatectl", "show", "-p", "NTP", "--value"], capture_output=True).stdout.strip() == b"yes"),
    ]

    all_ok = True
    for name, check_fn in checks:
        try:
            if ctx.dry_run or check_fn():
                typer.secho(f"  ✓ {name}", fg=typer.colors.GREEN)
            else:
                typer.secho(f"  ✗ {name}", fg=typer.colors.YELLOW)
                all_ok = False
        except Exception as e:
            typer.secho(f"  ✗ {name}: {e}", fg=typer.colors.YELLOW)
            all_ok = False

    return all_ok


def verify_hardening(ctx: ExecutionContext) -> bool:
    """Health check para modulo hardening."""
    logger.info("Verificando health check: hardening")
    typer.secho("\n=== Health Check: Hardening ===", fg=typer.colors.CYAN)

    services = ["fail2ban"]
    all_ok = True

    for service in services:
        ok, status = check_systemd_service(service, ctx)
        if ok:
            typer.secho(f"  ✓ {service}: {status}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ {service}: {status}", fg=typer.colors.YELLOW)
            all_ok = False

    return all_ok


def verify_kubernetes(ctx: ExecutionContext) -> bool:
    """Health check para modulo kubernetes."""
    logger.info("Verificando health check: kubernetes")
    typer.secho("\n=== Health Check: Kubernetes ===", fg=typer.colors.CYAN)

    services = ["kubelet", "containerd"]
    all_ok = True

    swap_ok, swap_msg = check_swap_disabled(ctx)
    if swap_ok:
        typer.secho(f"  ✓ Swap: {swap_msg}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Swap: {swap_msg}", fg=typer.colors.RED)
        all_ok = False

    for service in services:
        ok, status = check_systemd_service(service, ctx)
        if ok:
            typer.secho(f"  ✓ {service}: {status}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ {service}: {status}", fg=typer.colors.RED)
            all_ok = False

    # Verifica API server
    ok, msg = check_port_listening(6443, ctx)
    if ok:
        typer.secho(f"  ✓ API Server (6443): {msg}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ API Server (6443): {msg}", fg=typer.colors.RED)
        all_ok = False

    # Verifica node ready
    if not check_k8s_node_ready(ctx, timeout=180):
        all_ok = False

    return all_ok


def verify_calico(ctx: ExecutionContext) -> bool:
    """Health check para modulo calico."""
    logger.info("Verificando health check: calico")
    typer.secho("\n=== Health Check: Calico ===", fg=typer.colors.CYAN)

    return check_k8s_pods_in_namespace("kube-system", ctx, timeout=180)


def verify_helm_chart(release: str, namespace: str, ctx: ExecutionContext) -> bool:
    """Health check generico para charts Helm."""
    logger.info(f"Verificando health check: {release} no namespace {namespace}")
    typer.secho(f"\n=== Health Check: {release} ===", fg=typer.colors.CYAN)

    ok, status = check_helm_release(release, namespace, ctx)
    if ok:
        typer.secho(f"  ✓ Release {release}: {status}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Release {release}: {status}", fg=typer.colors.RED)
        return False

    return check_k8s_pods_in_namespace(namespace, ctx, timeout=180)


def verify_cert_manager(ctx: ExecutionContext) -> bool:
    """Health check completo para cert-manager."""
    logger.info("Verificando health check: cert-manager")
    typer.secho("\n=== Health Check: Cert-Manager ===", fg=typer.colors.CYAN)
    
    all_ok = True
    
    # Verifica release Helm
    ok, status = check_helm_release("cert-manager", CERT_NS, ctx)
    if ok:
        typer.secho(f"  ✓ Release cert-manager: {status}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Release cert-manager: {status}", fg=typer.colors.RED)
        return False
    
    # Verifica pods
    if not check_k8s_pods_in_namespace(CERT_NS, ctx, timeout=180):
        all_ok = False
    
    # Verifica CRDs
    if not ctx.dry_run:
        try:
            import subprocess
            result = subprocess.run(
                ["kubectl", "get", "crd", "certificates.cert-manager.io"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                typer.secho("  ✓ CRDs instalados", fg=typer.colors.GREEN)
            else:
                typer.secho("  ✗ CRDs não encontrados", fg=typer.colors.RED)
                all_ok = False
        except Exception as e:
            typer.secho(f"  ✗ Erro ao verificar CRDs: {e}", fg=typer.colors.RED)
            all_ok = False
    
    # Verifica webhook ready
    if not ctx.dry_run:
        try:
            import subprocess
            result = subprocess.run(
                [
                    "kubectl", "get", "deployment", "cert-manager-webhook",
                    "-n", CERT_NS,
                    "-o", "jsonpath={.status.readyReplicas}"
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ready = result.returncode == 0 and result.stdout.strip() and int(result.stdout.strip()) >= 1
            if ready:
                typer.secho("  ✓ Webhook pronto", fg=typer.colors.GREEN)
            else:
                typer.secho("  ✗ Webhook não está pronto", fg=typer.colors.RED)
                all_ok = False
        except Exception as e:
            typer.secho(f"  ✗ Erro ao verificar webhook: {e}", fg=typer.colors.RED)
            all_ok = False
    
    return all_ok


def verify_secrets(ctx: ExecutionContext) -> bool:
    """Health check para sealed-secrets e external-secrets."""
    typer.secho("\n=== Health Check: Secrets ===", fg=typer.colors.CYAN)

    sealed_ok = verify_helm_chart("sealed-secrets", SEALED_NS, ctx)
    eso_ok = verify_helm_chart("external-secrets", ESO_NS, ctx)

    return sealed_ok and eso_ok


# Mapeamento de modulos para funcoes de health check
HEALTH_CHECKS = {
    "essentials": verify_essentials,
    "hardening": verify_hardening,
    "kubernetes": verify_kubernetes,
    "calico": verify_calico,
    "prometheus": lambda ctx: verify_helm_chart("kube-prometheus-stack", "observability", ctx),
    "grafana": lambda ctx: verify_helm_chart("grafana", "observability", ctx),
    "loki": lambda ctx: verify_helm_chart("loki", "observability", ctx),
    "traefik": lambda ctx: verify_helm_chart("traefik", "traefik", ctx),
    "kong": lambda ctx: verify_helm_chart("kong", "kong", ctx),
    "minio": lambda ctx: verify_helm_chart("minio", "minio", ctx),
    "velero": lambda ctx: verify_helm_chart("velero", "velero", ctx),
    "kafka": lambda ctx: verify_helm_chart("kafka", "kafka", ctx),
    "cert_manager": verify_cert_manager,
    "secrets": verify_secrets,
}


# =============================================================================
# STATUS VALIDATION - Validação em tempo real para o menu interativo
# =============================================================================

def _quick_cmd(cmd: list[str], timeout: int = 5) -> tuple[bool, str]:
    """Executa comando rápido e retorna (sucesso, output)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def _check_namespace_exists(ns: str) -> bool:
    """Verifica se namespace existe."""
    ok, _ = _quick_cmd(["kubectl", "get", "ns", ns])
    return ok


def _check_pods_running(ns: str) -> tuple[bool, bool]:
    """Retorna (existe, todos_running)."""
    if not _check_namespace_exists(ns):
        return False, False
    ok, out = _quick_cmd(["kubectl", "get", "pods", "-n", ns, "-o", "jsonpath={.items[*].status.phase}"])
    if not ok or not out:
        return True, False  # ns existe mas sem pods ou erro
    phases = out.split()
    all_ok = all(p in ("Running", "Succeeded") for p in phases)
    return True, all_ok


def _check_helm_deployed(release: str, ns: str) -> tuple[bool, bool]:
    """Retorna (existe, deployed)."""
    ok, out = _quick_cmd(["helm", "status", release, "-n", ns, "--output", "json"], timeout=10)
    if not ok:
        return False, False
    try:
        import json
        data = json.loads(out)
        status = data.get("info", {}).get("status", "")
        return True, status == "deployed"
    except Exception:
        return False, False


def _check_systemd_active(service: str) -> bool:
    """Verifica se serviço systemd está ativo."""
    ok, out = _quick_cmd(["systemctl", "is-active", service])
    return ok and out == "active"


def _check_crd_exists(crd: str) -> bool:
    """Verifica se CRD existe."""
    ok, _ = _quick_cmd(["kubectl", "get", "crd", crd])
    return ok


def _check_cluster_secret_store() -> tuple[bool, bool]:
    """Verifica ClusterSecretStore. Retorna (existe, ready)."""
    ok, out = _quick_cmd(["kubectl", "get", "clustersecretstore", "-o", "jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"])
    if not ok:
        return False, False
    return True, "True" in out


# Status: "ok" = ✓, "error" = ✗, "not_installed" = -
ModuleStatus = str  # "ok" | "error" | "not_installed"


def validate_module_status(module: str) -> ModuleStatus:
    """Valida status de um módulo em tempo real."""
    validators = {
        "sanitize": _validate_sanitize,
        "bootstrap": _validate_bootstrap,
        "ssh_hardening": _validate_ssh_hardening,
        "hardening": _validate_hardening,
        "network": _validate_network,
        "essentials": _validate_essentials,
        "firewall": _validate_firewall,
        "vpn": _validate_vpn,
        "vpn_client": _validate_vpn_client,
        "internal_dns": _validate_internal_dns,
        "kubernetes": _validate_kubernetes,
        "calico": _validate_calico,
        "metallb": _validate_metallb,
        "traefik": _validate_traefik,
        "cert_manager": _validate_cert_manager,
        "istio": _validate_istio,
        "kong": _validate_kong,
        "minio": _validate_minio,
        "prometheus": _validate_prometheus,
        "grafana": _validate_grafana,
        "secrets": _validate_secrets,
        "loki": _validate_loki,
        "harbor": _validate_harbor,
        "harness": _validate_harness,
        "velero": _validate_velero,
        "kafka": _validate_kafka,
        "full_install": _validate_full_install,
    }
    
    validator = validators.get(module)
    if validator:
        try:
            return validator()
        except Exception:
            return "error"
    return "not_installed"


def _validate_sanitize() -> ModuleStatus:
    # Sanitize é idempotente, consideramos OK se bootstrap/k8s estiver funcionando
    return "ok"


def _validate_bootstrap() -> ModuleStatus:
    # Verifica se ferramentas estão instaladas
    tools = ["helm", "kubectl", "containerd"]
    for tool in tools:
        ok, _ = _quick_cmd(["which", tool])
        if not ok:
            return "not_installed"
    return "ok"


def _validate_ssh_hardening() -> ModuleStatus:
    # Verifica se SSH está rodando
    if _check_systemd_active("ssh") or _check_systemd_active("sshd"):
        return "ok"
    return "not_installed"


def _validate_hardening() -> ModuleStatus:
    if _check_systemd_active("fail2ban"):
        return "ok"
    return "not_installed"


def _validate_network() -> ModuleStatus:
    # Verifica se hostname está configurado
    ok, hostname = _quick_cmd(["hostname"])
    if ok and hostname:
        return "ok"
    return "not_installed"


def _validate_essentials() -> ModuleStatus:
    # Verifica NTP
    ok, out = _quick_cmd(["timedatectl", "show", "-p", "NTP", "--value"])
    if ok and out == "yes":
        return "ok"
    return "not_installed"


def _validate_firewall() -> ModuleStatus:
    if _check_systemd_active("ufw"):
        return "ok"
    return "not_installed"


def _validate_vpn() -> ModuleStatus:
    if _check_systemd_active("wg-quick@wg0"):
        return "ok"
    return "not_installed"


def _validate_vpn_client() -> ModuleStatus:
    # VPN client é gerenciado pelo VPN module
    if _check_systemd_active("wg-quick@wg0"):
        return "ok"
    return "not_installed"


def _validate_internal_dns() -> ModuleStatus:
    # Verifica se CoreDNS tem configuração de domínio interno (asgard.internal ou similar)
    ok, out = _quick_cmd(["kubectl", "get", "configmap", "coredns", "-n", "kube-system", "-o", "jsonpath={.data.Corefile}"])
    if ok and ".internal" in out:
        return "ok"
    # Fallback: verifica coredns-custom
    ok, _ = _quick_cmd(["kubectl", "get", "configmap", "coredns-custom", "-n", "kube-system"])
    if ok:
        return "ok"
    return "not_installed"


def _validate_kubernetes() -> ModuleStatus:
    if not _check_systemd_active("kubelet"):
        return "not_installed"
    if not _check_systemd_active("containerd"):
        return "error"
    # Verifica se node está ready
    ok, out = _quick_cmd(["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.conditions[?(@.type=='Ready')].status}"])
    if ok and "True" in out:
        return "ok"
    return "error"


def _validate_calico() -> ModuleStatus:
    exists, running = _check_pods_running("kube-system")
    if not exists:
        return "not_installed"
    # Verifica se calico-node está rodando
    ok, out = _quick_cmd(["kubectl", "get", "pods", "-n", "kube-system", "-l", "k8s-app=calico-node", "-o", "jsonpath={.items[*].status.phase}"])
    if ok and out and "Running" in out:
        return "ok"
    return "not_installed"


def _validate_metallb() -> ModuleStatus:
    exists, running = _check_pods_running("metallb-system")
    if not exists:
        return "not_installed"
    if running:
        return "ok"
    return "error"


def _validate_traefik() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("traefik", "traefik")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("traefik")
    if deployed and running:
        return "ok"
    return "error"


def _validate_cert_manager() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("cert-manager", "cert-manager")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("cert-manager")
    if deployed and running:
        return "ok"
    return "error"


def _validate_istio() -> ModuleStatus:
    exists, running = _check_pods_running("istio-system")
    if not exists:
        return "not_installed"
    if running:
        return "ok"
    return "error"


def _validate_kong() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("kong", "kong")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("kong")
    if deployed and running:
        return "ok"
    return "error"


def _validate_minio() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("minio", "minio")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("minio")
    if deployed and running:
        return "ok"
    return "error"


def _validate_prometheus() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("kube-prometheus-stack", "observability")
    if not exists:
        return "not_installed"
    ok, out = _quick_cmd(["kubectl", "get", "pods", "-n", "observability", "-l", "app.kubernetes.io/name=prometheus", "-o", "jsonpath={.items[*].status.phase}"])
    if ok and out and "Running" in out:
        return "ok"
    if exists:
        return "error"
    return "not_installed"


def _validate_grafana() -> ModuleStatus:
    ok, out = _quick_cmd(["kubectl", "get", "pods", "-n", "observability", "-l", "app.kubernetes.io/name=grafana", "-o", "jsonpath={.items[*].status.phase}"])
    if ok and out and "Running" in out:
        return "ok"
    return "not_installed"


def _validate_secrets() -> ModuleStatus:
    # Verifica Vault
    exists_vault, running_vault = _check_pods_running("vault")
    # Verifica External Secrets
    exists_eso, running_eso = _check_pods_running("external-secrets")
    # Verifica ClusterSecretStore
    css_exists, css_ready = _check_cluster_secret_store()
    
    if not exists_vault and not exists_eso:
        return "not_installed"
    
    if exists_vault and exists_eso and css_exists:
        if running_vault and running_eso and css_ready:
            return "ok"
        return "error"
    
    return "not_installed"


def _validate_loki() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("loki", "observability")
    if not exists:
        return "not_installed"
    # Loki usa label "app=loki" (não app.kubernetes.io/name)
    ok, out = _quick_cmd(["kubectl", "get", "pods", "-n", "observability", "-l", "app=loki", "-o", "jsonpath={.items[*].status.phase}"])
    if ok and out and "Running" in out:
        return "ok"
    return "error"


def _validate_harbor() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("harbor", "harbor")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("harbor")
    if deployed and running:
        return "ok"
    return "error"


def _validate_harness() -> ModuleStatus:
    exists, running = _check_pods_running("harness")
    if not exists:
        return "not_installed"
    if running:
        return "ok"
    return "error"


def _validate_velero() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("velero", "velero")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("velero")
    if deployed and running:
        return "ok"
    return "error"


def _validate_kafka() -> ModuleStatus:
    exists, deployed = _check_helm_deployed("kafka", "kafka")
    if not exists:
        return "not_installed"
    _, running = _check_pods_running("kafka")
    if deployed and running:
        return "ok"
    return "error"


def _validate_full_install() -> ModuleStatus:
    # Full install é um meta-módulo
    return "ok"


def get_all_module_statuses() -> dict[str, ModuleStatus]:
    """Retorna o status de todos os módulos."""
    from raijin_server.cli import MODULES
    statuses = {}
    for module in MODULES.keys():
        statuses[module] = validate_module_status(module)
    return statuses


def run_health_check(module: str, ctx: ExecutionContext) -> bool:
    """Executa health check para um modulo especifico."""
    if module not in HEALTH_CHECKS:
        logger.warning(f"Nenhum health check definido para modulo '{module}'")
        return True

    try:
        result = HEALTH_CHECKS[module](ctx)
        if result:
            logger.info(f"Health check '{module}': PASS")
        else:
            logger.warning(f"Health check '{module}': FAIL")
            ctx.warnings.append(f"Health check falhou para modulo '{module}'")
        return result
    except Exception as e:
        logger.error(f"Erro durante health check '{module}': {e}")
        ctx.errors.append(f"Erro no health check '{module}': {e}")
        return False
