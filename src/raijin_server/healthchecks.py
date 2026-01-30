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


def verify_apokolips_demo(ctx: ExecutionContext) -> bool:
    """Health check especifico para a landing page Apokolips."""
    namespace = "apokolips-demo"
    logger.info("Verificando health check: apokolips-demo")
    typer.secho("\n=== Health Check: Apokolips Demo ===", fg=typer.colors.CYAN)

    pods_ok = check_k8s_pods_in_namespace(namespace, ctx, timeout=120)
    if not pods_ok:
        return False
    if ctx.dry_run:
        return True

    try:
        import json

        result = subprocess.run(
            [
                "kubectl",
                "get",
                "ingress",
                "apokolips-demo",
                "-n",
                namespace,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            typer.secho("  ✗ Nao foi possivel consultar o ingress", fg=typer.colors.YELLOW)
            logger.warning("kubectl get ingress retornou codigo != 0 para apokolips-demo")
            return False

        data = json.loads(result.stdout)
        ingress_data = data.get("status", {}).get("loadBalancer", {}).get("ingress", [])
        address = ""
        if ingress_data:
            entry = ingress_data[0]
            address = entry.get("ip") or entry.get("hostname", "")

        if address:
            typer.secho(f"  ✓ LoadBalancer publicado ({address})", fg=typer.colors.GREEN)
            return True

        typer.secho("  ✗ LoadBalancer ainda sem IP/hostname", fg=typer.colors.YELLOW)
        return False
    except Exception as exc:
        typer.secho(f"  ✗ Erro ao verificar ingress: {exc}", fg=typer.colors.YELLOW)
        logger.error(f"Erro verificando ingress apokolips-demo: {exc}")
        return False


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
    "apokolips_demo": verify_apokolips_demo,
}


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
