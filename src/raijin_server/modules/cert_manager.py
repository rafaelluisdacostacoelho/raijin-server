"""Instala e configura cert-manager com emissores ACME (HTTP-01 ou DNS-01).

Este módulo oferece:
- Instalação do cert-manager via Helm com verificação completa de readiness
- Múltiplos provedores DNS (Cloudflare, Route53, DigitalOcean, Azure)
- Verificação REAL do webhook (testa com dry-run antes de aplicar)
- Modo não-interativo para automação completa
- Diagnóstico detalhado de problemas
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, List

import os

import typer

from raijin_server.utils import (
    ExecutionContext,
    ensure_tool,
    helm_upgrade_install,
    require_root,
    run_cmd,
    write_file,
    logger,
)

CHART_REPO = "https://charts.jetstack.io"
CHART_NAME = "cert-manager"
NAMESPACE = "cert-manager"
MANIFEST_PATH = Path("/tmp/raijin-cert-manager-issuer.yaml")
HELM_DATA_DIR = Path("/tmp/raijin-helm")
HELM_REPO_CONFIG = HELM_DATA_DIR / "repositories.yaml"
HELM_REPO_CACHE = HELM_DATA_DIR / "cache"

# Timeouts enxutos (falha rápida em redes rápidas)
WEBHOOK_READY_TIMEOUT = 240  # 4 minutos
POD_READY_TIMEOUT = 180      # 3 minutos
CRD_READY_TIMEOUT = 120      # 2 minutos


class DNSProvider(str, Enum):
    """Provedores DNS suportados para challenge DNS-01."""
    CLOUDFLARE = "cloudflare"
    ROUTE53 = "route53"
    DIGITALOCEAN = "digitalocean"
    AZURE = "azure"


class ChallengeType(str, Enum):
    """Tipos de challenge ACME suportados."""
    HTTP01 = "http01"
    DNS01 = "dns01"


@dataclass
class IssuerConfig:
    """Configuração para criação de ClusterIssuer."""
    name: str
    email: str
    staging: bool = False
    challenge_type: ChallengeType = ChallengeType.HTTP01
    ingress_class: str = "traefik"
    dns_provider: Optional[DNSProvider] = None
    secret_name: str = "dns-api-credentials"
    region: str = "us-east-1"
    hosted_zone_id: str = ""
    resource_group: str = ""
    subscription_id: str = ""
    tenant_id: str = ""
    client_id: str = ""
    # Credentials (transient, not persisted)
    _credentials: dict = field(default_factory=dict)


def _get_acme_server(staging: bool) -> str:
    """Retorna URL do servidor ACME."""
    if staging:
        return "https://acme-staging-v02.api.letsencrypt.org/directory"
    return "https://acme-v02.api.letsencrypt.org/directory"


def _helm_env() -> dict:
    """Garante diretórios de cache/config do Helm isolados em /tmp para evitar erros de permissão."""
    HELM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    HELM_REPO_CACHE.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "HELM_REPOSITORY_CONFIG": str(HELM_REPO_CONFIG),
        "HELM_REPOSITORY_CACHE": str(HELM_REPO_CACHE),
    }


# =============================================================================
# Builders de Manifests YAML
# =============================================================================

def _build_http01_issuer(config: IssuerConfig) -> str:
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {config.name}
spec:
  acme:
    email: {config.email}
    server: {_get_acme_server(config.staging)}
    privateKeySecretRef:
      name: {config.name}-account-key
    solvers:
      - http01:
          ingress:
            class: {config.ingress_class}
"""


def _build_cloudflare_issuer(config: IssuerConfig) -> str:
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {config.name}
spec:
  acme:
    email: {config.email}
    server: {_get_acme_server(config.staging)}
    privateKeySecretRef:
      name: {config.name}-account-key
    solvers:
      - dns01:
          cloudflare:
            apiTokenSecretRef:
              name: {config.secret_name}
              key: api-token
"""


def _build_route53_issuer(config: IssuerConfig) -> str:
    hosted_zone = ""
    if config.hosted_zone_id:
        hosted_zone = f"\n            hostedZoneID: {config.hosted_zone_id}"
    
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {config.name}
spec:
  acme:
    email: {config.email}
    server: {_get_acme_server(config.staging)}
    privateKeySecretRef:
      name: {config.name}-account-key
    solvers:
      - dns01:
          route53:
            region: {config.region}{hosted_zone}
            accessKeyIDSecretRef:
              name: {config.secret_name}
              key: access-key-id
            secretAccessKeySecretRef:
              name: {config.secret_name}
              key: secret-access-key
"""


def _build_digitalocean_issuer(config: IssuerConfig) -> str:
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {config.name}
spec:
  acme:
    email: {config.email}
    server: {_get_acme_server(config.staging)}
    privateKeySecretRef:
      name: {config.name}-account-key
    solvers:
      - dns01:
          digitalocean:
            tokenSecretRef:
              name: {config.secret_name}
              key: access-token
"""


def _build_azure_issuer(config: IssuerConfig) -> str:
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {config.name}
spec:
  acme:
    email: {config.email}
    server: {_get_acme_server(config.staging)}
    privateKeySecretRef:
      name: {config.name}-account-key
    solvers:
      - dns01:
          azureDNS:
            subscriptionID: {config.subscription_id}
            resourceGroupName: {config.resource_group}
            hostedZoneName: {config.name}
            environment: AzurePublicCloud
            clientID: {config.client_id}
            tenantID: {config.tenant_id}
            clientSecretSecretRef:
              name: {config.secret_name}
              key: client-secret
"""


def _build_secret(config: IssuerConfig) -> Optional[str]:
    """Gera Secret baseado no provider DNS."""
    if config.challenge_type != ChallengeType.DNS01:
        return None
    
    creds = config._credentials
    
    if config.dns_provider == DNSProvider.CLOUDFLARE:
        return f"""apiVersion: v1
kind: Secret
metadata:
  name: {config.secret_name}
  namespace: {NAMESPACE}
type: Opaque
stringData:
  api-token: {creds.get('api_token', '')}
"""
    
    elif config.dns_provider == DNSProvider.ROUTE53:
        return f"""apiVersion: v1
kind: Secret
metadata:
  name: {config.secret_name}
  namespace: {NAMESPACE}
type: Opaque
stringData:
  access-key-id: {creds.get('access_key', '')}
  secret-access-key: {creds.get('secret_key', '')}
"""
    
    elif config.dns_provider == DNSProvider.DIGITALOCEAN:
        return f"""apiVersion: v1
kind: Secret
metadata:
  name: {config.secret_name}
  namespace: {NAMESPACE}
type: Opaque
stringData:
  access-token: {creds.get('token', '')}
"""
    
    elif config.dns_provider == DNSProvider.AZURE:
        return f"""apiVersion: v1
kind: Secret
metadata:
  name: {config.secret_name}
  namespace: {NAMESPACE}
type: Opaque
stringData:
  client-secret: {creds.get('client_secret', '')}
"""
    
    return None


# =============================================================================
# Verificações de Estado
# =============================================================================

def _check_cluster_available(ctx: ExecutionContext) -> bool:
    """Verifica se o cluster Kubernetes está acessível."""
    if ctx.dry_run:
        return True
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_crds_installed() -> bool:
    """Verifica se os CRDs do cert-manager estão instalados."""
    required_crds = [
        "certificates.cert-manager.io",
        "clusterissuers.cert-manager.io",
        "issuers.cert-manager.io",
    ]
    try:
        for crd in required_crds:
            result = subprocess.run(
                ["kubectl", "get", "crd", crd],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False
        return True
    except Exception:
        return False


def _check_deployment_ready(name: str, namespace: str) -> bool:
    """Verifica se um deployment está com todas as replicas ready."""
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "deployment", name,
                "-n", namespace,
                "-o", "jsonpath={.status.readyReplicas}/{.spec.replicas}"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        
        parts = result.stdout.strip().split("/")
        if len(parts) != 2:
            return False
        
        ready = int(parts[0]) if parts[0] else 0
        desired = int(parts[1]) if parts[1] else 1
        return ready >= desired
    except Exception:
        return False


def _check_webhook_endpoint_ready() -> bool:
    """Verifica se o endpoint do webhook tem IPs atribuídos."""
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "endpoints", "cert-manager-webhook",
                "-n", NAMESPACE,
                "-o", "jsonpath={.subsets[0].addresses[0].ip}"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _test_webhook_connectivity() -> bool:
    """Testa se o webhook está realmente respondendo usando dry-run."""
    try:
        # Cria um ClusterIssuer de teste para validar o webhook
        test_manifest = """apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: test-webhook-connectivity
spec:
  acme:
    email: test@test.com
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: test-key
    solvers:
      - http01:
          ingress:
            class: nginx
"""
        # Usa --dry-run=server para testar se o webhook responde
        result = subprocess.run(
            ["kubectl", "apply", "--dry-run=server", "-f", "-"],
            input=test_manifest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Se passou no dry-run, o webhook está funcionando
        if result.returncode == 0:
            return True
        
        # Verifica se o erro é de conexão com webhook
        stderr = result.stderr.lower()
        if "connection refused" in stderr or "no endpoints" in stderr:
            return False
        
        # Outros erros (validação, etc) significam que o webhook respondeu
        return True
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _wait_for_webhook_ready(ctx: ExecutionContext, timeout: int = WEBHOOK_READY_TIMEOUT) -> bool:
    """Aguarda até que o webhook do cert-manager esteja totalmente operacional."""
    if ctx.dry_run:
        typer.echo("[dry-run] Aguardando webhook...")
        return True
    
    typer.secho("\n⏳ Aguardando cert-manager ficar pronto...", fg=typer.colors.CYAN)
    
    start_time = time.time()
    interval = 15
    
    stages = [
        ("CRDs instalados", _check_crds_installed),
        ("Deployment cert-manager ready", lambda: _check_deployment_ready("cert-manager", NAMESPACE)),
        ("Deployment cert-manager-webhook ready", lambda: _check_deployment_ready("cert-manager-webhook", NAMESPACE)),
        ("Deployment cert-manager-cainjector ready", lambda: _check_deployment_ready("cert-manager-cainjector", NAMESPACE)),
        ("Endpoint webhook disponível", _check_webhook_endpoint_ready),
        ("Webhook respondendo (teste de conectividade)", _test_webhook_connectivity),
    ]
    
    for stage_name, check_fn in stages:
        typer.echo(f"\n  → Verificando: {stage_name}")
        
        while True:
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            
            if remaining <= 0:
                typer.secho(f"    ✗ TIMEOUT após {timeout}s", fg=typer.colors.RED)
                return False
            
            try:
                if check_fn():
                    typer.secho(f"    ✓ {stage_name}", fg=typer.colors.GREEN)
                    break
            except Exception as e:
                logger.debug(f"Verificação falhou: {e}")
            
            typer.echo(f"    ... aguardando ({elapsed}s / {timeout}s)")
            time.sleep(interval)
    
    typer.secho("\n✓ Cert-manager totalmente operacional!", fg=typer.colors.GREEN, bold=True)
    return True


# =============================================================================
# Instalação e Configuração
# =============================================================================

def _test_helm_repo_connectivity(ctx: ExecutionContext) -> bool:
    """Testa conectividade com o repositório Helm antes de instalar."""
    if ctx.dry_run:
        return True
    
    logger.info("Testando conectividade com charts.jetstack.io")
    typer.echo("  [1/5] Testando conectividade com charts.jetstack.io...")
    
    try:
        start = time.time()
        result = subprocess.run(
            ["curl", "-sI", "--connect-timeout", "15", f"{CHART_REPO}/index.yaml"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        elapsed = time.time() - start
        
        if result.returncode == 0 and "200" in result.stdout:
            logger.info(f"Repositório Helm acessível em {elapsed:.2f}s")
            typer.secho(f"  ✓ Repositório Helm acessível ({elapsed:.2f}s)", fg=typer.colors.GREEN)
            return True
        else:
            logger.error(f"Repositório retornou erro: {result.stdout[:200]}")
            typer.secho(f"  ✗ Repositório retornou erro: {result.stdout[:100]}", fg=typer.colors.RED)
            return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao conectar com charts.jetstack.io")
        typer.secho("  ✗ Timeout ao conectar com charts.jetstack.io (>15s)", fg=typer.colors.RED)
        return False
    except Exception as e:
        logger.error(f"Erro de conectividade: {e}")
        typer.secho(f"  ✗ Erro de conectividade: {e}", fg=typer.colors.RED)
        return False


def _test_image_registry_connectivity(ctx: ExecutionContext) -> bool:
    """Testa conectividade com o registry de imagens."""
    if ctx.dry_run:
        return True
    
    logger.info("Testando conectividade com quay.io (registry de imagens)")
    typer.echo("  [2/5] Testando conectividade com quay.io (registry de imagens)...")
    
    try:
        start = time.time()
        result = subprocess.run(
            ["curl", "-sI", "--connect-timeout", "15", "https://quay.io/v2/"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        elapsed = time.time() - start
        
        # quay.io retorna 401 para /v2/ sem auth, mas isso significa que está acessível
        if result.returncode == 0 and ("200" in result.stdout or "401" in result.stdout):
            logger.info(f"Registry quay.io acessível em {elapsed:.2f}s")
            typer.secho(f"  ✓ Registry quay.io acessível ({elapsed:.2f}s)", fg=typer.colors.GREEN)
            return True
        else:
            logger.warning(f"Registry pode estar inacessível: {result.stdout[:100]}")
            typer.secho(f"  ⚠ Registry pode estar inacessível", fg=typer.colors.YELLOW)
            return True  # Não bloqueia, apenas avisa
    except Exception as e:
        logger.warning(f"Não foi possível testar registry: {e}")
        typer.secho(f"  ⚠ Não foi possível testar registry: {e}", fg=typer.colors.YELLOW)
        return True  # Não bloqueia


def _add_helm_repo(ctx: ExecutionContext) -> bool:
    """Adiciona e atualiza o repositório Helm."""
    if ctx.dry_run:
        typer.echo("  [3/5] [dry-run] Adicionando repositório Helm jetstack...")
        return True
    
    logger.info("Adicionando repositório Helm jetstack")
    typer.echo("  [3/5] Adicionando repositório Helm jetstack...")
    
    try:
        start = time.time()
        
        # Adiciona repo
        result = subprocess.run(
            ["helm", "repo", "add", "jetstack", CHART_REPO, "--force-update"],
            capture_output=True,
            text=True,
            timeout=60,
            env=_helm_env(),
        )
        
        if result.returncode != 0:
            logger.error(f"Falha ao adicionar repo: {result.stderr}")
            typer.secho(f"  ✗ Falha ao adicionar repo: {result.stderr[:100]}", fg=typer.colors.RED)
            return False
        
        elapsed_add = time.time() - start
        logger.info(f"Repo adicionado em {elapsed_add:.2f}s")
        typer.echo(f"      Repo adicionado ({elapsed_add:.2f}s)")
        
        # Atualiza repo
        typer.echo("      Atualizando índice do repositório...")
        start = time.time()
        
        result = subprocess.run(
            ["helm", "repo", "update", "jetstack"],
            capture_output=True,
            text=True,
            timeout=120,
            env=_helm_env(),
        )
        
        elapsed_update = time.time() - start
        
        if result.returncode != 0:
            logger.error(f"Falha ao atualizar repo: {result.stderr}")
            typer.secho(f"  ✗ Falha ao atualizar repo: {result.stderr[:100]}", fg=typer.colors.RED)
            return False
        
        logger.info(f"Repo atualizado em {elapsed_update:.2f}s")
        typer.secho(f"  ✓ Repositório configurado ({elapsed_add + elapsed_update:.2f}s total)", fg=typer.colors.GREEN)
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao configurar repositório Helm")
        typer.secho("  ✗ Timeout ao configurar repositório (>60s)", fg=typer.colors.RED)
        return False
    except Exception as e:
        logger.error(f"Erro ao configurar repo: {e}")
        typer.secho(f"  ✗ Erro: {e}", fg=typer.colors.RED)
        return False


def _run_helm_install(ctx: ExecutionContext, attempt: int = 1) -> bool:
    """Executa o helm upgrade --install, com uma tentativa de retry para repo/config."""
    if ctx.dry_run:
        typer.echo("  [4/5] [dry-run] Executando helm upgrade --install...")
        return True
    
    logger.info("Executando helm upgrade --install cert-manager")
    typer.echo("  [4/5] Executando helm upgrade --install cert-manager...")
    typer.echo("        (isso pode levar vários minutos)")
    
    cmd = [
        "helm", "upgrade", "--install", "cert-manager", "jetstack/cert-manager",
        "--repo", CHART_REPO,
        "-n", NAMESPACE,
        "--create-namespace",
        "--set", "installCRDs=true",
        "--set", "webhook.timeoutSeconds=30",
        "--set", "startupapicheck.timeout=5m",
        "--set", "startupapicheck.enabled=true",
        "--set", "webhook.replicaCount=1",
        "--set", "cainjector.replicaCount=1",
        "--wait",
        "--timeout", "15m",
        "--debug",  # Mais logs
    ]
    
    logger.info(f"Comando: {' '.join(cmd)}")
    
    try:
        start = time.time()
        
        # Executa com output em tempo real para ver progresso
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=_helm_env(),
        )
        
        output_lines = []
        last_log_time = time.time()
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                output_lines.append(line)
                logger.debug(line.strip())
                
                # Mostra progresso a cada 30s
                if time.time() - last_log_time > 30:
                    elapsed = int(time.time() - start)
                    typer.echo(f"        ... ainda instalando ({elapsed}s)")
                    last_log_time = time.time()
        
        elapsed = time.time() - start
        return_code = process.poll()
        
        if return_code == 0:
            logger.info(f"Helm install concluído em {elapsed:.2f}s")
            typer.secho(f"  ✓ Helm install concluído ({elapsed:.2f}s)", fg=typer.colors.GREEN)
            return True
        else:
            output = "".join(output_lines[-20:])  # Últimas 20 linhas
            logger.error(f"Helm install falhou (código {return_code}): {output}")
            typer.secho(f"  ✗ Helm install falhou (código {return_code})", fg=typer.colors.RED)

            needs_repo_retry = "repo jetstack not found" in output.lower() or "repositories.yaml" in output.lower()
            if needs_repo_retry and attempt == 1:
                typer.echo("  → Reconfigurando repositório Helm e tentando novamente...")
                if _add_helm_repo(ctx):
                    return _run_helm_install(ctx, attempt=2)

            # Mostra as últimas linhas do erro
            typer.echo("\n  Últimas linhas do log:")
            for line in output_lines[-10:]:
                typer.echo(f"    {line.strip()}")
            
            return False
            
    except Exception as e:
        logger.error(f"Erro durante helm install: {e}")
        typer.secho(f"  ✗ Erro: {e}", fg=typer.colors.RED)
        return False


def _verify_installation(ctx: ExecutionContext) -> bool:
    """Verifica se os pods estão rodando."""
    if ctx.dry_run:
        typer.echo("  [5/5] [dry-run] Verificando instalação...")
        return True
    
    logger.info("Verificando pods do cert-manager")
    typer.echo("  [5/5] Verificando pods do cert-manager...")
    
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", NAMESPACE, "-o", "wide"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            typer.echo(f"\n{result.stdout}")
            
            # Verifica se todos estão Running
            if "Running" in result.stdout and "0/1" not in result.stdout:
                logger.info("Todos os pods estão Running")
                typer.secho("  ✓ Todos os pods estão Running", fg=typer.colors.GREEN)
                return True
            else:
                logger.warning("Alguns pods podem não estar prontos")
                typer.secho("  ⚠ Alguns pods podem não estar prontos", fg=typer.colors.YELLOW)
                return True  # Não falha, o wait_for_webhook vai verificar
        else:
            logger.error(f"Erro ao verificar pods: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao verificar pods: {e}")
        return False


def _install_cert_manager_helm(ctx: ExecutionContext) -> bool:
    """Instala cert-manager via Helm com logs detalhados."""
    typer.secho("\n📦 Instalando cert-manager via Helm...", fg=typer.colors.CYAN, bold=True)
    logger.info("Iniciando instalação do cert-manager")
    
    start_total = time.time()
    
    # Etapa 1: Testa conectividade com repo Helm
    if not _test_helm_repo_connectivity(ctx):
        typer.secho(
            "\n⚠ Problema de conectividade com o repositório Helm.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("  Teste manual: curl -sI https://charts.jetstack.io/index.yaml")
        if not typer.confirm("Tentar instalar mesmo assim?", default=False):
            return False
    
    # Etapa 2: Testa conectividade com registry de imagens
    _test_image_registry_connectivity(ctx)
    
    # Etapa 3: Adiciona e atualiza repo Helm
    if not _add_helm_repo(ctx):
        return False
    
    # Etapa 4: Executa helm install
    if not _run_helm_install(ctx):
        _show_diagnostic_info(ctx)
        return False
    
    # Etapa 5: Verifica instalação
    _verify_installation(ctx)
    
    elapsed_total = time.time() - start_total
    logger.info(f"Instalação do cert-manager concluída em {elapsed_total:.2f}s")
    typer.secho(f"\n✓ Instalação concluída em {elapsed_total:.2f}s", fg=typer.colors.GREEN)
    
    return True


def _show_diagnostic_info(ctx: ExecutionContext) -> None:
    """Mostra informações de diagnóstico quando falha."""
    if ctx.dry_run:
        return
    
    typer.secho("\n🔍 Informações de diagnóstico:", fg=typer.colors.YELLOW, bold=True)
    
    # Pods
    typer.echo("\n  Pods:")
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", NAMESPACE, "-o", "wide"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                typer.echo(f"    {line}")
    except Exception:
        typer.echo("    (não foi possível obter pods)")
    
    # Eventos recentes
    typer.echo("\n  Eventos recentes:")
    try:
        result = subprocess.run(
            ["kubectl", "get", "events", "-n", NAMESPACE, "--sort-by=.lastTimestamp"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            for line in lines[-10:]:  # Últimos 10 eventos
                typer.echo(f"    {line[:120]}")
    except Exception:
        typer.echo("    (não foi possível obter eventos)")
    
    # Helm status
    typer.echo("\n  Helm release status:")
    try:
        result = subprocess.run(
            ["helm", "status", "cert-manager", "-n", NAMESPACE],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n")[:15]:
                typer.echo(f"    {line}")
    except Exception:
        typer.echo("    (não foi possível obter status do Helm)")


def _apply_manifest_with_retry(
    manifest: str,
    ctx: ExecutionContext,
    description: str = "manifest",
    max_retries: int = 10,
    retry_interval: int = 30,
) -> bool:
    """Aplica um manifest com retry inteligente."""
    if ctx.dry_run:
        typer.echo(f"[dry-run] Aplicando {description}")
        return True
    
    manifest_path = MANIFEST_PATH
    manifest_path.write_text(manifest)
    
    for attempt in range(1, max_retries + 1):
        typer.echo(f"\n  Aplicando {description} (tentativa {attempt}/{max_retries})...")
        
        try:
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                typer.secho(f"  ✓ {description} aplicado com sucesso!", fg=typer.colors.GREEN)
                return True
            
            stderr = result.stderr.lower()
            
            # Verifica se é erro de webhook
            if "connection refused" in stderr or "failed to call webhook" in stderr:
                typer.secho(
                    f"  ⚠ Webhook ainda não está pronto...",
                    fg=typer.colors.YELLOW,
                )
                if attempt < max_retries:
                    typer.echo(f"    Aguardando {retry_interval}s antes de tentar novamente...")
                    time.sleep(retry_interval)
                    continue
            
            # Outro tipo de erro
            typer.secho(f"  ✗ Erro: {result.stderr[:200]}", fg=typer.colors.RED)
            if attempt < max_retries:
                time.sleep(retry_interval)
            
        except subprocess.TimeoutExpired:
            typer.secho("  ⚠ Timeout ao aplicar manifest", fg=typer.colors.YELLOW)
            if attempt < max_retries:
                time.sleep(retry_interval)
        except Exception as e:
            typer.secho(f"  ✗ Erro inesperado: {e}", fg=typer.colors.RED)
            if attempt < max_retries:
                time.sleep(retry_interval)
    
    typer.secho(f"✗ Falha ao aplicar {description} após {max_retries} tentativas", fg=typer.colors.RED)
    return False


def _build_issuer_manifests(config: IssuerConfig) -> str:
    """Constrói todos os manifests necessários para o issuer."""
    manifests = []
    
    # Secret (se necessário)
    secret = _build_secret(config)
    if secret:
        manifests.append(secret)
    
    # ClusterIssuer
    if config.challenge_type == ChallengeType.HTTP01:
        manifests.append(_build_http01_issuer(config))
    elif config.dns_provider == DNSProvider.CLOUDFLARE:
        manifests.append(_build_cloudflare_issuer(config))
    elif config.dns_provider == DNSProvider.ROUTE53:
        manifests.append(_build_route53_issuer(config))
    elif config.dns_provider == DNSProvider.DIGITALOCEAN:
        manifests.append(_build_digitalocean_issuer(config))
    elif config.dns_provider == DNSProvider.AZURE:
        manifests.append(_build_azure_issuer(config))
    
    return "---\n".join(manifests)


# =============================================================================
# Interface Interativa
# =============================================================================

def _collect_issuer_config_interactive() -> Optional[IssuerConfig]:
    """Coleta configuração do issuer interativamente."""
    typer.secho("\n🔧 Configuração do ClusterIssuer", fg=typer.colors.CYAN, bold=True)
    
    email = typer.prompt(
        "Email para ACME (Let's Encrypt)",
        default="admin@example.com",
    )
    
    if "@" not in email or "example.com" in email:
        typer.secho(
            "⚠ Use um email válido para receber notificações de expiração",
            fg=typer.colors.YELLOW,
        )
        if not typer.confirm("Continuar mesmo assim?", default=False):
            return None
    
    solver = typer.prompt(
        "Tipo de challenge (http01/dns01)",
        default="http01",
    ).lower()
    
    staging = typer.confirm(
        "Usar servidor de staging? (para testes)",
        default=True,
    )
    
    if staging:
        typer.secho(
            "ℹ Staging gera certificados de teste (não válidos para produção)",
            fg=typer.colors.CYAN,
        )
    
    config = IssuerConfig(name="", email=email, staging=staging)
    
    if solver == "dns01":
        config.challenge_type = ChallengeType.DNS01
        
        typer.echo("\nProvedores DNS disponíveis:")
        typer.echo("  1. Cloudflare")
        typer.echo("  2. AWS Route53")
        typer.echo("  3. DigitalOcean")
        typer.echo("  4. Azure DNS")
        
        choice = typer.prompt("Escolha (1-4)", default="1")
        
        if choice == "1":
            config.dns_provider = DNSProvider.CLOUDFLARE
            config.name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-cloudflare")
            config.secret_name = typer.prompt("Nome do Secret", default="cloudflare-api-token")
            config._credentials["api_token"] = typer.prompt("API Token do Cloudflare", hide_input=True)
            
        elif choice == "2":
            config.dns_provider = DNSProvider.ROUTE53
            config.name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-route53")
            config.secret_name = typer.prompt("Nome do Secret", default="route53-credentials")
            config.region = typer.prompt("AWS Region", default="us-east-1")
            config.hosted_zone_id = typer.prompt("Hosted Zone ID (opcional)", default="")
            config._credentials["access_key"] = typer.prompt("AWS Access Key ID", hide_input=True)
            config._credentials["secret_key"] = typer.prompt("AWS Secret Access Key", hide_input=True)
            
        elif choice == "3":
            config.dns_provider = DNSProvider.DIGITALOCEAN
            config.name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-digitalocean")
            config.secret_name = typer.prompt("Nome do Secret", default="digitalocean-token")
            config._credentials["token"] = typer.prompt("DigitalOcean API Token", hide_input=True)
            
        elif choice == "4":
            config.dns_provider = DNSProvider.AZURE
            config.name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-azure")
            config.secret_name = typer.prompt("Nome do Secret", default="azure-dns-credentials")
            config.subscription_id = typer.prompt("Azure Subscription ID")
            config.resource_group = typer.prompt("Resource Group")
            config.tenant_id = typer.prompt("Tenant ID")
            config.client_id = typer.prompt("Client ID (App Registration)")
            config._credentials["client_secret"] = typer.prompt("Client Secret", hide_input=True)
        else:
            typer.secho("Opção inválida", fg=typer.colors.RED)
            return None
    else:
        config.challenge_type = ChallengeType.HTTP01
        config.name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-http")
        config.ingress_class = typer.prompt("IngressClass", default="traefik")
    
    return config


def _print_next_steps(config: IssuerConfig) -> None:
    """Exibe próximos passos após configuração."""
    typer.secho("\n📚 Próximos Passos", fg=typer.colors.CYAN, bold=True)
    typer.echo("─" * 50)
    
    typer.echo(f"""
Para usar certificados TLS em seus Ingresses:

1. Adicione a annotation no Ingress:
   annotations:
     cert-manager.io/cluster-issuer: "{config.name}"

2. Configure o TLS no Ingress:
   tls:
     - hosts:
         - seu-dominio.com
       secretName: seu-dominio-tls

3. Verifique o status do certificado:
   kubectl get certificate -A
   kubectl describe certificate <nome> -n <namespace>

4. Para debug de problemas:
   kubectl describe clusterissuer {config.name}
   kubectl get challenges -A
   kubectl get orders -A
""")
    
    if config.staging:
        typer.secho(
            "⚠ Você está usando o servidor STAGING!\n"
            "   Os certificados NÃO são válidos para produção.\n"
            "   Após testar, recrie o issuer sem staging.",
            fg=typer.colors.YELLOW,
        )
    
    typer.echo("─" * 50)


# =============================================================================
# Status e Diagnóstico
# =============================================================================

def _get_cert_manager_status(ctx: ExecutionContext) -> dict:
    """Obtém status detalhado do cert-manager."""
    status = {
        "installed": False,
        "version": "",
        "pods": [],
        "webhook_ready": False,
        "crds_installed": False,
        "issuers": [],
        "certificates": [],
    }
    
    if ctx.dry_run:
        return status
    
    try:
        # Verifica versão via Helm
        result = subprocess.run(
            ["helm", "list", "-n", NAMESPACE, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            releases = json.loads(result.stdout)
            for r in releases:
                if r.get("name") == "cert-manager":
                    status["installed"] = True
                    status["version"] = r.get("app_version", "")
                    break
        
        # Verifica pods
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "-o", "jsonpath={range .items[*]}{.metadata.name}:{.status.phase}\\n{end}"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    name, phase = line.split(":", 1)
                    status["pods"].append({"name": name, "phase": phase})
        
        status["webhook_ready"] = _test_webhook_connectivity()
        status["crds_installed"] = _check_crds_installed()
        
        # Lista ClusterIssuers
        result = subprocess.run(
            ["kubectl", "get", "clusterissuers", "-o", "jsonpath={.items[*].metadata.name}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            status["issuers"] = result.stdout.strip().split()
        
        # Lista Certificates
        result = subprocess.run(
            [
                "kubectl", "get", "certificates", "-A",
                "-o", "jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name}:{.status.conditions[0].status}\\n{end}"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    name, ready = line.split(":", 1)
                    status["certificates"].append({"name": name, "ready": ready})
    
    except Exception as e:
        logger.error(f"Erro ao obter status do cert-manager: {e}")
    
    return status


def _print_status(status: dict) -> None:
    """Exibe status formatado do cert-manager."""
    typer.secho("\n📊 Status do Cert-Manager", fg=typer.colors.CYAN, bold=True)
    typer.echo("─" * 50)
    
    if status["installed"]:
        typer.secho(f"  ✓ Instalado: versão {status['version']}", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Não instalado", fg=typer.colors.RED)
        return
    
    typer.echo("\n  Pods:")
    for pod in status["pods"]:
        color = typer.colors.GREEN if pod["phase"] == "Running" else typer.colors.YELLOW
        typer.secho(f"    • {pod['name']}: {pod['phase']}", fg=color)
    
    if status["webhook_ready"]:
        typer.secho("  ✓ Webhook: Operacional", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Webhook: Não está respondendo", fg=typer.colors.RED)
    
    if status["crds_installed"]:
        typer.secho("  ✓ CRDs: Instalados", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ CRDs: Não encontrados", fg=typer.colors.RED)
    
    if status["issuers"]:
        typer.echo("\n  ClusterIssuers:")
        for issuer in status["issuers"]:
            typer.echo(f"    • {issuer}")
    else:
        typer.echo("\n  ClusterIssuers: Nenhum configurado")
    
    if status["certificates"]:
        typer.echo("\n  Certificates:")
        for cert in status["certificates"]:
            color = typer.colors.GREEN if cert["ready"] == "True" else typer.colors.YELLOW
            typer.secho(f"    • {cert['name']}: {cert['ready']}", fg=color)
    
    typer.echo("─" * 50)


def _diagnose_problems(ctx: ExecutionContext) -> None:
    """Diagnóstico detalhado de problemas comuns."""
    typer.secho("\n🔍 Diagnóstico de Problemas", fg=typer.colors.YELLOW, bold=True)
    
    if ctx.dry_run:
        typer.echo("[dry-run] Diagnóstico ignorado")
        return
    
    problems = []
    
    # Verifica conectividade do cluster
    if not _check_cluster_available(ctx):
        problems.append("Cluster Kubernetes não acessível")
    
    # Verifica namespace
    result = subprocess.run(
        ["kubectl", "get", "namespace", NAMESPACE],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        problems.append(f"Namespace '{NAMESPACE}' não existe")
    
    # Verifica eventos recentes com erros
    typer.echo("\n  Eventos recentes:")
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "events", "-n", NAMESPACE,
                "--sort-by=.lastTimestamp",
                "--field-selector=type!=Normal",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n")[:10]:
                typer.echo(f"    {line[:120]}")
        else:
            typer.echo("    Nenhum evento de erro recente")
    except Exception:
        pass
    
    # Verifica logs do webhook
    typer.echo("\n  Logs recentes do webhook:")
    try:
        result = subprocess.run(
            [
                "kubectl", "logs", "-n", NAMESPACE,
                "-l", "app.kubernetes.io/component=webhook",
                "--tail=15"
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n")[-10:]:
                typer.echo(f"    {line[:120]}")
        else:
            typer.echo("    Nenhum log disponível")
    except Exception:
        pass
    
    # Verifica describe dos deployments
    typer.echo("\n  Status dos Deployments:")
    for deploy in ["cert-manager", "cert-manager-webhook", "cert-manager-cainjector"]:
        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "deployment", deploy, "-n", NAMESPACE,
                    "-o", "jsonpath={.status.conditions[?(@.type=='Available')].status}"
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            status = result.stdout.strip() if result.returncode == 0 else "Unknown"
            color = typer.colors.GREEN if status == "True" else typer.colors.RED
            typer.secho(f"    {deploy}: Available={status}", fg=color)
        except Exception:
            typer.secho(f"    {deploy}: Erro ao verificar", fg=typer.colors.RED)
    
    if problems:
        typer.secho("\n  Problemas detectados:", fg=typer.colors.RED)
        for p in problems:
            typer.echo(f"    ✗ {p}")
    else:
        typer.secho("\n  Nenhum problema óbvio detectado", fg=typer.colors.GREEN)


# =============================================================================
# Entry Points
# =============================================================================

def run(ctx: ExecutionContext) -> None:
    """Execução principal do módulo cert-manager."""
    require_root(ctx)
    ensure_tool("helm", ctx, install_hint="Instale helm ou use --dry-run para simular.")
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou use --dry-run para simular.")

    # Verifica cluster
    if not _check_cluster_available(ctx):
        typer.secho(
            "✗ Cluster Kubernetes não acessível. Execute 'kubernetes' primeiro.",
            fg=typer.colors.RED,
        )
        ctx.errors.append("cert-manager: cluster não acessível")
        raise typer.Exit(code=1)

    # Mostra status atual
    status = _get_cert_manager_status(ctx)
    _print_status(status)
    
    # Verifica se já está instalado e funcionando
    if status["installed"] and status["webhook_ready"]:
        typer.echo("\nCert-manager já está instalado e operacional.")
        if not typer.confirm("Deseja adicionar um novo ClusterIssuer?", default=True):
            return
    else:
        # Instala cert-manager
        if not _install_cert_manager_helm(ctx):
            _diagnose_problems(ctx)
            raise typer.Exit(code=1)
        
        # Aguarda ficar totalmente operacional
        if not ctx.dry_run:
            if not _wait_for_webhook_ready(ctx):
                typer.secho(
                    "\n✗ Cert-manager não ficou pronto no tempo esperado.",
                    fg=typer.colors.RED,
                )
                _diagnose_problems(ctx)
                raise typer.Exit(code=1)
    
    # Configura ClusterIssuer
    config = _collect_issuer_config_interactive()
    if config is None:
        typer.secho("Configuração cancelada", fg=typer.colors.YELLOW)
        return
    
    # Constrói e aplica manifests
    manifests = _build_issuer_manifests(config)
    
    if _apply_manifest_with_retry(manifests, ctx, f"ClusterIssuer '{config.name}'"):
        _print_next_steps(config)
        typer.secho("\n✓ Cert-manager configurado com sucesso!", fg=typer.colors.GREEN, bold=True)
    else:
        _diagnose_problems(ctx)
        ctx.errors.append("cert-manager: falha ao criar ClusterIssuer")


def status(ctx: ExecutionContext) -> None:
    """Exibe status detalhado do cert-manager."""
    ensure_tool("kubectl", ctx)
    status_data = _get_cert_manager_status(ctx)
    _print_status(status_data)


def diagnose(ctx: ExecutionContext) -> None:
    """Executa diagnóstico completo do cert-manager."""
    ensure_tool("kubectl", ctx)
    status_data = _get_cert_manager_status(ctx)
    _print_status(status_data)
    _diagnose_problems(ctx)


def install_only(ctx: ExecutionContext) -> bool:
    """Instala apenas o cert-manager sem configurar issuer (para uso em full_install)."""
    require_root(ctx)
    ensure_tool("helm", ctx)
    ensure_tool("kubectl", ctx)
    
    if not _check_cluster_available(ctx):
        ctx.errors.append("cert-manager: cluster não acessível")
        return False
    
    # Verifica se já está instalado
    status = _get_cert_manager_status(ctx)
    if status["installed"] and status["webhook_ready"]:
        typer.secho("✓ Cert-manager já está instalado e operacional", fg=typer.colors.GREEN)
        return True
    
    # Instala
    if not _install_cert_manager_helm(ctx):
        return False
    
    # Aguarda
    if not ctx.dry_run:
        return _wait_for_webhook_ready(ctx)
    
    return True


def create_issuer(
    ctx: ExecutionContext,
    name: str,
    email: str,
    challenge_type: str = "http01",
    staging: bool = True,
    ingress_class: str = "traefik",
    dns_provider: Optional[str] = None,
    secret_name: str = "dns-api-credentials",
    credentials: Optional[dict] = None,
) -> bool:
    """Cria um ClusterIssuer programaticamente (para uso em automação)."""
    ensure_tool("kubectl", ctx)
    
    config = IssuerConfig(
        name=name,
        email=email,
        staging=staging,
        challenge_type=ChallengeType(challenge_type),
        ingress_class=ingress_class,
        dns_provider=DNSProvider(dns_provider) if dns_provider else None,
        secret_name=secret_name,
    )
    
    if credentials:
        config._credentials = credentials
    
    manifests = _build_issuer_manifests(config)
    return _apply_manifest_with_retry(manifests, ctx, f"ClusterIssuer '{name}'")

