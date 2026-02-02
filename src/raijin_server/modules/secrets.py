"""Automacao de HashiCorp Vault e External Secrets Operator (production-ready).

Instala Vault com MinIO backend para persistencia e External Secrets Operator
para sincronizar segredos do Vault para Secrets nativos do Kubernetes.

Arquitetura:
- Vault: Gerenciamento centralizado de segredos com MinIO como storage backend
- External Secrets Operator: Sincroniza segredos do Vault para K8s Secrets
- Aplicações: Usam Secrets nativos do K8s (transparente)
"""

import base64
import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    ensure_tool,
    helm_upgrade_install,
    require_root,
    run_cmd,
    write_file,
)
from raijin_server.minio_utils import get_or_create_minio_user

VAULT_NAMESPACE = "vault"
ESO_NAMESPACE = "external-secrets"


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


def _check_existing_vault(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica se existe instalacao do Vault."""
    result = run_cmd(
        ["helm", "status", "vault", "-n", namespace],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_existing_external_secrets(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica se existe instalacao do External Secrets."""
    result = run_cmd(
        ["helm", "status", "external-secrets", "-n", namespace],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_vault(ctx: ExecutionContext, namespace: str) -> None:
    """Remove instalacao anterior do Vault."""
    typer.echo("Removendo instalacao anterior do Vault...")
    
    run_cmd(
        ["helm", "uninstall", "vault", "-n", namespace],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _uninstall_external_secrets(ctx: ExecutionContext, namespace: str) -> None:
    """Remove instalacao anterior do External Secrets."""
    typer.echo("Removendo instalacao anterior do External Secrets...")
    
    run_cmd(
        ["helm", "uninstall", "external-secrets", "-n", namespace],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_pods_ready(ctx: ExecutionContext, namespace: str, label: str, timeout: int = 120) -> bool:
    """Aguarda pods ficarem Ready."""
    typer.echo(f"Aguardando pods com label {label} ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
                "-l", label,
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
                    typer.secho(f"  Pods {label} Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(5)
    
    typer.secho(f"  Timeout aguardando pods {label}.", fg=typer.colors.YELLOW)
    return False


def _get_minio_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    """Obtem ou cria credenciais específicas do MinIO para Vault.
    
    Esta função cria um usuário MinIO dedicado para o Vault com acesso
    restrito apenas ao bucket 'vault-storage'.
    """
    return get_or_create_minio_user(
        ctx=ctx,
        app_name="vault",
        buckets=["vault-storage"],
        namespace=VAULT_NAMESPACE,
    )


def _initialize_vault(ctx: ExecutionContext, vault_ns: str, node_ip: str) -> tuple[str, str]:
    """Inicializa o Vault com 1 key/1 threshold e retorna root token e unseal key."""
    typer.echo("\nInicializando Vault...")
    
    # Usa 1 key com threshold 1 para simplificar (produção pode usar 5/3)
    result = run_cmd(
        [
            "kubectl", "-n", vault_ns, "exec", "vault-0", "--", 
            "vault", "operator", "init", 
            "-key-shares=1", "-key-threshold=1", "-format=json"
        ],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        typer.secho("Falha ao inicializar Vault.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    import json
    init_data = json.loads(result.stdout)
    root_token = init_data["root_token"]
    unseal_key = init_data["unseal_keys_b64"][0]
    
    # Salva keys localmente
    vault_keys_path = Path("/etc/vault/keys.json")
    vault_keys_path.parent.mkdir(parents=True, exist_ok=True)
    vault_keys_path.write_text(json.dumps(init_data, indent=2))
    typer.secho(f"\n✓ Vault keys salvas em {vault_keys_path}", fg=typer.colors.GREEN)
    
    # Salva credenciais em secret K8s para uso do ESO
    _save_vault_credentials_to_k8s(ctx, vault_ns, root_token, unseal_key)
    
    typer.secho("⚠️  IMPORTANTE: Guarde essas keys em local seguro!", fg=typer.colors.YELLOW, bold=True)
    
    return root_token, unseal_key


def _save_vault_credentials_to_k8s(ctx: ExecutionContext, vault_ns: str, root_token: str, unseal_key: str) -> None:
    """Salva credenciais do Vault em secret K8s."""
    typer.echo("Salvando credenciais do Vault em secret K8s...")
    
    # Codifica em base64
    token_b64 = base64.b64encode(root_token.encode()).decode()
    key_b64 = base64.b64encode(unseal_key.encode()).decode()
    
    secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: vault-init-credentials
  namespace: {vault_ns}
type: Opaque
data:
  root-token: {token_b64}
  unseal-key: {key_b64}
"""
    
    secret_path = Path("/tmp/raijin-vault-credentials.yaml")
    write_file(secret_path, secret_yaml, ctx)
    
    run_cmd(
        ["kubectl", "apply", "-f", str(secret_path)],
        ctx,
    )
    
    typer.secho("✓ Credenciais salvas em secret vault-init-credentials.", fg=typer.colors.GREEN)


def _unseal_vault(ctx: ExecutionContext, vault_ns: str, unseal_key: str) -> None:
    """Destrava o Vault usando a unseal key."""
    typer.echo("\nDesbloqueando Vault...")
    
    run_cmd(
        ["kubectl", "-n", vault_ns, "exec", "vault-0", "--", "vault", "operator", "unseal", unseal_key],
        ctx,
    )
    
    typer.secho("✓ Vault desbloqueado.", fg=typer.colors.GREEN)


def _enable_kv_secrets(ctx: ExecutionContext, vault_ns: str, root_token: str) -> None:
    """Habilita KV v2 secrets engine."""
    typer.echo("\nHabilitando KV v2 secrets engine...")
    
    run_cmd(
        [
            "kubectl", "-n", vault_ns, "exec", "vault-0", "--", 
            "vault", "secrets", "enable", "-path=secret", "kv-v2"
        ],
        ctx,
        env={"VAULT_TOKEN": root_token},
        check=False,  # Pode já estar habilitado
    )
    
    typer.secho("✓ KV v2 habilitado em path 'secret'.", fg=typer.colors.GREEN)


def _configure_kubernetes_auth(ctx: ExecutionContext, vault_ns: str, root_token: str) -> None:
    """Configura autenticação Kubernetes no Vault."""
    typer.echo("\nConfigurando autenticação Kubernetes...")
    
    # Habilita kubernetes auth
    run_cmd(
        ["kubectl", "-n", vault_ns, "exec", "vault-0", "--", "vault", "auth", "enable", "kubernetes"],
        ctx,
        env={"VAULT_TOKEN": root_token},
        check=False,
    )
    
    # Configura kubernetes auth
    run_cmd(
        [
            "kubectl", "-n", vault_ns, "exec", "vault-0", "--",
            "sh", "-c",
            "vault write auth/kubernetes/config " +
            "kubernetes_host=https://$KUBERNETES_PORT_443_TCP_ADDR:443"
        ],
        ctx,
        env={"VAULT_TOKEN": root_token},
    )
    
    typer.secho("✓ Autenticação Kubernetes configurada.", fg=typer.colors.GREEN)


def _create_eso_policy_and_role(ctx: ExecutionContext, vault_ns: str, root_token: str, eso_ns: str) -> None:
    """Cria policy e role para External Secrets Operator."""
    typer.echo("\nCriando policy e role para ESO...")
    
    # Policy para ler todos os secrets
    policy = """path "secret/data/*" {
  capabilities = ["read"]
}"""
    
    run_cmd(
        ["kubectl", "-n", vault_ns, "exec", "vault-0", "--", "vault", "policy", "write", "eso-policy", "-"],
        ctx,
        env={"VAULT_TOKEN": root_token},
        input=policy,
    )
    
    # Role vinculando serviceaccount do ESO
    run_cmd(
        [
            "kubectl", "-n", vault_ns, "exec", "vault-0", "--",
            "vault", "write", "auth/kubernetes/role/eso-role",
            "bound_service_account_names=external-secrets",
            f"bound_service_account_namespaces={eso_ns}",
            "policies=eso-policy",
            "ttl=24h"
        ],
        ctx,
        env={"VAULT_TOKEN": root_token},
    )
    
    typer.secho("✓ Policy 'eso-policy' e role 'eso-role' criadas.", fg=typer.colors.GREEN)


def _create_secretstore_example(ctx: ExecutionContext, vault_ns: str, eso_ns: str, node_ip: str) -> None:
    """Cria exemplo de ClusterSecretStore e ExternalSecret."""
    typer.echo("\nCriando exemplo de ClusterSecretStore...")
    
    secretstore_yaml = f"""apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.{vault_ns}.svc:8200"
      path: "secret"
      version: "v2"
      auth:
        tokenSecretRef:
          namespace: "{vault_ns}"
          name: "vault-init-credentials"
          key: "root-token"
"""
    
    secretstore_path = Path("/tmp/raijin-vault-secretstore.yaml")
    write_file(secretstore_path, secretstore_yaml, ctx)
    
    run_cmd(
        ["kubectl", "apply", "-f", str(secretstore_path)],
        ctx,
    )
    
    typer.secho("✓ ClusterSecretStore 'vault-backend' criado.", fg=typer.colors.GREEN)


def _create_example_secret(ctx: ExecutionContext, vault_ns: str, root_token: str) -> None:
    """Cria um secret de exemplo no Vault."""
    typer.echo("\nCriando secret de exemplo no Vault...")
    
    run_cmd(
        [
            "kubectl", "-n", vault_ns, "exec", "vault-0", "--",
            "vault", "kv", "put", "secret/example",
            "username=admin",
            "password=supersecret123"
        ],
        ctx,
        env={"VAULT_TOKEN": root_token},
    )
    
    typer.secho("✓ Secret 'secret/example' criado no Vault.", fg=typer.colors.GREEN)
    
    # Cria ExternalSecret de exemplo
    external_secret_yaml = """apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: example-secret
  namespace: default
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: example-secret
    creationPolicy: Owner
  data:
  - secretKey: username
    remoteRef:
      key: secret/example
      property: username
  - secretKey: password
    remoteRef:
      key: secret/example
      property: password
"""
    
    external_secret_path = Path("/tmp/raijin-vault-externalsecret.yaml")
    write_file(external_secret_path, external_secret_yaml, ctx)
    
    run_cmd(
        ["kubectl", "apply", "-f", str(external_secret_path)],
        ctx,
    )
    
    typer.secho("✓ ExternalSecret 'example-secret' criado no namespace default.", fg=typer.colors.GREEN)
    
    # Aguarda sincronização
    time.sleep(5)
    
    # Verifica se o Secret foi criado
    result = run_cmd(
        ["kubectl", "-n", "default", "get", "secret", "example-secret"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.secho("\n✓ Secret sincronizado com sucesso! Teste com:", fg=typer.colors.GREEN)
        typer.echo("  kubectl -n default get secret example-secret -o yaml")


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    ensure_tool("helm", ctx, install_hint="Instale helm ou habilite dry-run.")

    typer.echo("Instalando HashiCorp Vault + External Secrets Operator...")

    vault_ns = typer.prompt("Namespace para Vault", default=VAULT_NAMESPACE)
    eso_ns = typer.prompt("Namespace para External Secrets", default=ESO_NAMESPACE)

    node_name = _detect_node_name(ctx)
    
    # Detecta IP do node para acesso ao MinIO
    result = run_cmd(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}"],
        ctx,
        check=False,
    )
    node_ip = result.stdout.strip() if result.returncode == 0 else "192.168.1.81"
    
    minio_host = typer.prompt("MinIO host (interno)", default="minio.minio.svc:9000")
    access_key, secret_key = _get_minio_credentials(ctx)

    # ========== HashiCorp Vault ==========
    typer.secho("\n== HashiCorp Vault ==", fg=typer.colors.CYAN, bold=True)

    if _check_existing_vault(ctx, vault_ns):
        cleanup = typer.confirm(
            "Instalacao anterior do Vault detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_vault(ctx, vault_ns)

    # Credenciais são obtidas automaticamente via get_or_create_minio_user
    # que já cria o bucket 'vault-storage' e o usuário 'vault-user'

    vault_values_yaml = f"""server:
  ha:
    enabled: true
    replicas: 1
    raft:
      enabled: false
  
  standalone:
    enabled: true
    config: |
      ui = true
      
      listener "tcp" {{
        tls_disable = 1
        address = "[::]:8200"
        cluster_address = "[::]:8201"
      }}
      
      storage "s3" {{
        endpoint = "http://{minio_host}"
        bucket = "vault-storage"
        access_key = "{access_key}"
        secret_key = "{secret_key}"
        s3_force_path_style = true
      }}
      
      api_addr = "http://vault.{vault_ns}.svc.cluster.local:8200"
      cluster_addr = "http://vault-0.vault-internal:8201"
  
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  
  nodeSelector:
    kubernetes.io/hostname: {node_name}
  
  resources:
    requests:
      memory: 256Mi
      cpu: 250m
    limits:
      memory: 512Mi

ui:
  enabled: true
  serviceType: "NodePort"
  serviceNodePort: 30820

injector:
  enabled: false
"""

    vault_values_path = Path("/tmp/raijin-vault-values.yaml")
    write_file(vault_values_path, vault_values_yaml, ctx)

    helm_upgrade_install(
        "vault",
        "vault",
        vault_ns,
        ctx,
        repo="hashicorp",
        repo_url="https://helm.releases.hashicorp.com",
        create_namespace=True,
        extra_args=["-f", str(vault_values_path)],
    )

    if not ctx.dry_run:
        _wait_for_pods_ready(ctx, vault_ns, "app.kubernetes.io/name=vault", timeout=180)
        
        # Inicializa Vault (retorna root_token e unseal_key)
        root_token, unseal_key = _initialize_vault(ctx, vault_ns, node_ip)
        
        # Destrava Vault
        _unseal_vault(ctx, vault_ns, unseal_key)
        
        # Configura Vault
        _enable_kv_secrets(ctx, vault_ns, root_token)

    # ========== External Secrets Operator ==========
    typer.secho("\n== External Secrets Operator ==", fg=typer.colors.CYAN, bold=True)

    if _check_existing_external_secrets(ctx, eso_ns):
        cleanup = typer.confirm(
            "Instalacao anterior do External Secrets detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_external_secrets(ctx, eso_ns)

    eso_values_yaml = f"""installCRDs: true
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
  - key: node-role.kubernetes.io/master
    operator: Exists
    effect: NoSchedule
nodeSelector:
  kubernetes.io/hostname: {node_name}
webhook:
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  nodeSelector:
    kubernetes.io/hostname: {node_name}
certController:
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  nodeSelector:
    kubernetes.io/hostname: {node_name}
resources:
  requests:
    memory: 64Mi
    cpu: 50m
  limits:
    memory: 128Mi
"""

    eso_values_path = Path("/tmp/raijin-external-secrets-values.yaml")
    write_file(eso_values_path, eso_values_yaml, ctx)

    helm_upgrade_install(
        "external-secrets",
        "external-secrets",
        eso_ns,
        ctx,
        repo="external-secrets",
        repo_url="https://charts.external-secrets.io",
        create_namespace=True,
        extra_args=["-f", str(eso_values_path)],
    )

    if not ctx.dry_run:
        _wait_for_pods_ready(ctx, eso_ns, "app.kubernetes.io/name=external-secrets", timeout=120)
        
        # Cria ClusterSecretStore (usa tokenSecretRef, não precisa de Kubernetes auth)
        _create_secretstore_example(ctx, vault_ns, eso_ns, node_ip)
        _create_example_secret(ctx, vault_ns, root_token)

    typer.secho("\n✓ Vault + External Secrets Operator instalado com sucesso!", fg=typer.colors.GREEN, bold=True)
    
    typer.secho("\n=== Acesso ao Vault UI ===", fg=typer.colors.CYAN)
    typer.echo(f"URL: http://{node_ip}:30820")
    typer.echo(f"Token: {root_token if not ctx.dry_run else '<root-token>'}")
    
    typer.secho("\n=== Como usar ===", fg=typer.colors.CYAN)
    typer.echo("1. Criar segredo no Vault:")
    typer.echo(f"   kubectl -n {vault_ns} exec vault-0 -- vault kv put secret/myapp username=admin password=secret123")
    
    typer.echo("\n2. Criar ExternalSecret:")
    typer.echo("   kubectl apply -f - <<EOF")
    typer.echo("   apiVersion: external-secrets.io/v1")
    typer.echo("   kind: ExternalSecret")
    typer.echo("   metadata:")
    typer.echo("     name: myapp-secret")
    typer.echo("   spec:")
    typer.echo("     secretStoreRef:")
    typer.echo("       name: vault-backend")
    typer.echo("       kind: ClusterSecretStore")
    typer.echo("     target:")
    typer.echo("       name: myapp-secret")
    typer.echo("     data:")
    typer.echo("     - secretKey: username")
    typer.echo("       remoteRef:")
    typer.echo("         key: secret/myapp")
    typer.echo("         property: username")
    typer.echo("   EOF")
    
    typer.echo("\n3. Secret será sincronizado automaticamente!")
    typer.echo("   kubectl get secret myapp-secret -o yaml")
    
    typer.secho("\n=== Recuperar Credenciais ===", fg=typer.colors.CYAN)
    typer.echo("Via arquivo local:")
    typer.echo("  cat /etc/vault/keys.json")
    typer.echo("\nVia Kubernetes Secret:")
    typer.echo(f"  kubectl -n {vault_ns} get secret vault-init-credentials -o jsonpath='{{.data.root-token}}' | base64 -d")
    typer.echo(f"  kubectl -n {vault_ns} get secret vault-init-credentials -o jsonpath='{{.data.unseal-key}}' | base64 -d")
    
    typer.secho("\n⚠️  IMPORTANTE:", fg=typer.colors.YELLOW, bold=True)
    typer.echo("- Faça backup das credenciais em local seguro!")
    typer.echo(f"- Após reboot do Vault, use: kubectl -n {vault_ns} exec vault-0 -- vault operator unseal <unseal-key>")

