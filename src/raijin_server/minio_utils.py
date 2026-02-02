"""Utilitários centralizados para gerenciamento de usuários e políticas MinIO.

Este módulo implementa o princípio do menor privilégio para aplicações que
usam MinIO como backend de storage, criando usuários específicos com acesso
limitado aos buckets necessários.

Aplicações suportadas:
- vault-user   → vault-storage bucket
- velero-user  → velero-backups bucket
- harbor-user  → harbor-registry, harbor-chartmuseum, harbor-jobservice buckets
- loki-user    → loki-chunks, loki-ruler, loki-admin buckets (futuro)

Uso:
    from raijin_server.minio_utils import get_or_create_minio_user

    # Cria usuário específico para a aplicação
    access_key, secret_key = get_or_create_minio_user(
        ctx=ctx,
        app_name="harbor",
        buckets=["harbor-registry", "harbor-chartmuseum", "harbor-jobservice"],
    )
"""

import base64
import json
import secrets
import time
from pathlib import Path
from typing import Optional

import typer

from raijin_server.utils import ExecutionContext, run_cmd


# Configuração de usuários por aplicação
MINIO_APP_USERS = {
    "vault": {
        "username": "vault-user",
        "buckets": ["vault-storage"],
        "description": "Usuário para HashiCorp Vault backend storage",
    },
    "velero": {
        "username": "velero-user",
        "buckets": ["velero-backups"],
        "description": "Usuário para Velero backup storage",
    },
    "harbor": {
        "username": "harbor-user",
        "buckets": ["harbor-registry", "harbor-chartmuseum", "harbor-jobservice"],
        "description": "Usuário para Harbor container registry",
    },
    "loki": {
        "username": "loki-user",
        "buckets": ["loki-chunks", "loki-ruler", "loki-admin"],
        "description": "Usuário para Loki logs storage",
    },
}


def _generate_password(length: int = 32) -> str:
    """Gera senha aleatória segura."""
    return secrets.token_urlsafe(length)[:length]


def _get_minio_root_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    """Obtém credenciais root do MinIO do Secret do K8s."""
    # Tenta secret 'minio' primeiro (padrão do Helm chart)
    result = run_cmd(
        ["kubectl", "-n", "minio", "get", "secret", "minio", "-o", "jsonpath={.data.rootUser}"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0 and result.stdout:
        root_user = base64.b64decode(result.stdout.strip()).decode("utf-8")
        
        result = run_cmd(
            ["kubectl", "-n", "minio", "get", "secret", "minio", "-o", "jsonpath={.data.rootPassword}"],
            ctx,
            check=False,
        )
        
        if result.returncode == 0 and result.stdout:
            root_password = base64.b64decode(result.stdout.strip()).decode("utf-8")
            return root_user, root_password
    
    # Fallback para secret minio-credentials
    result = run_cmd(
        ["kubectl", "-n", "minio", "get", "secret", "minio-credentials", "-o", "jsonpath={.data.accesskey}"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0 and result.stdout:
        access_key = base64.b64decode(result.stdout.strip()).decode("utf-8")
        
        result = run_cmd(
            ["kubectl", "-n", "minio", "get", "secret", "minio-credentials", "-o", "jsonpath={.data.secretkey}"],
            ctx,
            check=False,
        )
        
        if result.returncode == 0 and result.stdout:
            secret_key = base64.b64decode(result.stdout.strip()).decode("utf-8")
            return access_key, secret_key
    
    raise RuntimeError("Não foi possível obter credenciais root do MinIO. Verifique se o MinIO está instalado.")


def _setup_mc_alias(ctx: ExecutionContext, root_user: str, root_password: str) -> bool:
    """Configura alias 'local' no mc dentro do pod MinIO."""
    result = run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "mc", "alias", "set", "local", "http://localhost:9000", root_user, root_password,
        ],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_user_exists(ctx: ExecutionContext, username: str) -> bool:
    """Verifica se usuário já existe no MinIO."""
    result = run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "admin", "user", "info", "local", username],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _create_minio_user(ctx: ExecutionContext, username: str, password: str) -> bool:
    """Cria usuário no MinIO."""
    result = run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "mc", "admin", "user", "add", "local", username, password,
        ],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _create_bucket_policy(ctx: ExecutionContext, policy_name: str, buckets: list[str]) -> bool:
    """Cria política de acesso restrita aos buckets especificados."""
    # Cria documento de policy S3
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                    "s3:ListBucketMultipartUploads",
                ],
                "Resource": [f"arn:aws:s3:::{bucket}" for bucket in buckets],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListMultipartUploadParts",
                    "s3:AbortMultipartUpload",
                ],
                "Resource": [f"arn:aws:s3:::{bucket}/*" for bucket in buckets],
            },
        ],
    }
    
    policy_json = json.dumps(policy_doc)
    
    # Salva policy em arquivo temporário dentro do pod
    result = run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "sh", "-c", f"echo '{policy_json}' > /tmp/{policy_name}.json",
        ],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        return False
    
    # Cria policy no MinIO
    result = run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "mc", "admin", "policy", "create", "local", policy_name, f"/tmp/{policy_name}.json",
        ],
        ctx,
        check=False,
    )
    
    # Se policy já existe, atualiza
    if result.returncode != 0:
        result = run_cmd(
            [
                "kubectl", "-n", "minio", "exec", "minio-0", "--",
                "mc", "admin", "policy", "remove", "local", policy_name,
            ],
            ctx,
            check=False,
        )
        result = run_cmd(
            [
                "kubectl", "-n", "minio", "exec", "minio-0", "--",
                "mc", "admin", "policy", "create", "local", policy_name, f"/tmp/{policy_name}.json",
            ],
            ctx,
            check=False,
        )
    
    return result.returncode == 0


def _attach_policy_to_user(ctx: ExecutionContext, username: str, policy_name: str) -> bool:
    """Associa política ao usuário."""
    result = run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "mc", "admin", "policy", "attach", "local", policy_name, "--user", username,
        ],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _create_bucket(ctx: ExecutionContext, bucket_name: str) -> bool:
    """Cria bucket se não existir."""
    # Verifica se bucket existe
    result = run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "ls", f"local/{bucket_name}"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.echo(f"    Bucket '{bucket_name}' já existe.")
        return True
    
    # Cria bucket
    result = run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "mb", f"local/{bucket_name}"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.secho(f"    ✓ Bucket '{bucket_name}' criado.", fg=typer.colors.GREEN)
        return True
    
    typer.secho(f"    ✗ Falha ao criar bucket '{bucket_name}'.", fg=typer.colors.RED)
    return False


def _save_credentials_to_k8s_secret(
    ctx: ExecutionContext,
    app_name: str,
    username: str,
    password: str,
    namespace: str,
) -> bool:
    """Salva credenciais do usuário em um Secret K8s."""
    import subprocess
    import tempfile
    from pathlib import Path
    
    secret_name = f"minio-{app_name}-credentials"
    
    # Cria ou atualiza secret
    secret_manifest = f"""apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/managed-by: raijin-server
    app.kubernetes.io/component: minio-credentials
    app.kubernetes.io/part-of: {app_name}
type: Opaque
stringData:
  accesskey: "{username}"
  secretkey: "{password}"
  AWS_ACCESS_KEY_ID: "{username}"
  AWS_SECRET_ACCESS_KEY: "{password}"
"""
    
    # Usa arquivo temporário para aplicar o manifest
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            tmp.write(secret_manifest)
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        result = run_cmd(
            ["kubectl", "apply", "-f", str(tmp_path)],
            ctx,
            check=False,
        )
        return result.returncode == 0
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _get_credentials_from_k8s_secret(
    ctx: ExecutionContext,
    app_name: str,
    namespace: str,
) -> Optional[tuple[str, str]]:
    """Recupera credenciais do Secret K8s se existir."""
    secret_name = f"minio-{app_name}-credentials"
    
    result = run_cmd(
        ["kubectl", "-n", namespace, "get", "secret", secret_name, "-o", "jsonpath={.data.accesskey}"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0 and result.stdout:
        access_key = base64.b64decode(result.stdout.strip()).decode("utf-8")
        
        result = run_cmd(
            ["kubectl", "-n", namespace, "get", "secret", secret_name, "-o", "jsonpath={.data.secretkey}"],
            ctx,
            check=False,
        )
        
        if result.returncode == 0 and result.stdout:
            secret_key = base64.b64decode(result.stdout.strip()).decode("utf-8")
            return access_key, secret_key
    
    return None


def get_or_create_minio_user(
    ctx: ExecutionContext,
    app_name: str,
    buckets: Optional[list[str]] = None,
    namespace: Optional[str] = None,
    force_recreate: bool = False,
) -> tuple[str, str]:
    """Obtém ou cria usuário MinIO específico para uma aplicação.
    
    Esta função implementa o princípio do menor privilégio, criando um usuário
    MinIO com acesso restrito apenas aos buckets necessários para a aplicação.
    
    Args:
        ctx: Contexto de execução
        app_name: Nome da aplicação (vault, velero, harbor, loki)
        buckets: Lista de buckets para criar/permitir acesso (opcional, usa padrão se não fornecido)
        namespace: Namespace K8s para salvar o secret (opcional, usa app_name se não fornecido)
        force_recreate: Se True, recria usuário mesmo se já existir
    
    Returns:
        Tupla (access_key, secret_key) com as credenciais do usuário
    
    Raises:
        RuntimeError: Se não conseguir criar usuário ou MinIO não estiver disponível
    """
    typer.echo(f"\n🔐 Configurando usuário MinIO para '{app_name}'...")
    
    # Obtém configuração padrão se não fornecida
    if app_name in MINIO_APP_USERS:
        config = MINIO_APP_USERS[app_name]
        username = config["username"]
        if buckets is None:
            buckets = config["buckets"]
        if namespace is None:
            namespace = app_name
    else:
        username = f"{app_name}-user"
        if buckets is None:
            buckets = [f"{app_name}-data"]
        if namespace is None:
            namespace = app_name
    
    policy_name = f"{app_name}-policy"
    
    # Verifica se já existe secret com credenciais
    if not force_recreate:
        existing_creds = _get_credentials_from_k8s_secret(ctx, app_name, namespace)
        if existing_creds:
            typer.secho(f"  ✓ Credenciais existentes encontradas para '{app_name}'.", fg=typer.colors.GREEN)
            return existing_creds
    
    if ctx.dry_run:
        typer.echo(f"  [DRY-RUN] Criaria usuário '{username}' com acesso a: {', '.join(buckets)}")
        return (username, "dry-run-password")
    
    # Obtém credenciais root
    try:
        root_user, root_password = _get_minio_root_credentials(ctx)
    except RuntimeError as e:
        typer.secho(f"  ✗ {e}", fg=typer.colors.RED)
        raise
    
    # Configura mc alias
    if not _setup_mc_alias(ctx, root_user, root_password):
        raise RuntimeError("Falha ao configurar mc alias no MinIO.")
    
    # Cria buckets necessários
    typer.echo(f"  Criando buckets para '{app_name}'...")
    for bucket in buckets:
        _create_bucket(ctx, bucket)
    
    # Verifica se usuário já existe
    user_exists = _check_user_exists(ctx, username)
    
    if user_exists and not force_recreate:
        # Recupera senha existente do secret se disponível
        existing = _get_credentials_from_k8s_secret(ctx, app_name, namespace)
        if existing:
            typer.secho(f"  ✓ Usuário '{username}' já existe.", fg=typer.colors.GREEN)
            return existing
    
    # Gera nova senha
    password = _generate_password(32)
    
    # Cria ou recria usuário
    if user_exists:
        typer.echo(f"  Recriando usuário '{username}'...")
        # Remove usuário antigo
        run_cmd(
            ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "admin", "user", "remove", "local", username],
            ctx,
            check=False,
        )
    
    typer.echo(f"  Criando usuário '{username}'...")
    if not _create_minio_user(ctx, username, password):
        raise RuntimeError(f"Falha ao criar usuário MinIO '{username}'.")
    
    # Cria política de acesso
    typer.echo(f"  Criando política '{policy_name}'...")
    if not _create_bucket_policy(ctx, policy_name, buckets):
        raise RuntimeError(f"Falha ao criar política '{policy_name}'.")
    
    # Associa política ao usuário
    typer.echo(f"  Associando política ao usuário...")
    if not _attach_policy_to_user(ctx, username, policy_name):
        raise RuntimeError(f"Falha ao associar política ao usuário '{username}'.")
    
    # Garante que namespace existe
    run_cmd(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        ctx,
        check=False,
    )
    run_cmd(
        ["kubectl", "create", "namespace", namespace],
        ctx,
        check=False,
    )
    
    # Salva credenciais em Secret K8s
    typer.echo(f"  Salvando credenciais em Secret K8s...")
    if not _save_credentials_to_k8s_secret(ctx, app_name, username, password, namespace):
        typer.secho(f"  ⚠️  Falha ao salvar secret, mas usuário foi criado.", fg=typer.colors.YELLOW)
    
    typer.secho(f"  ✓ Usuário '{username}' criado com acesso a: {', '.join(buckets)}", fg=typer.colors.GREEN)
    
    return (username, password)


def list_minio_users(ctx: ExecutionContext) -> list[dict]:
    """Lista todos os usuários MinIO (exceto root)."""
    try:
        root_user, root_password = _get_minio_root_credentials(ctx)
        _setup_mc_alias(ctx, root_user, root_password)
    except RuntimeError:
        return []
    
    result = run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "admin", "user", "ls", "local", "--json"],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        return []
    
    users = []
    for line in (result.stdout or "").strip().split("\n"):
        if line.strip():
            try:
                data = json.loads(line)
                if data.get("accessKey"):
                    users.append({
                        "username": data.get("accessKey"),
                        "status": data.get("userStatus", "enabled"),
                        "policy": data.get("policyName", ""),
                    })
            except json.JSONDecodeError:
                pass
    
    return users


def delete_minio_user(ctx: ExecutionContext, app_name: str) -> bool:
    """Remove usuário MinIO e seu secret associado."""
    if app_name in MINIO_APP_USERS:
        username = MINIO_APP_USERS[app_name]["username"]
    else:
        username = f"{app_name}-user"
    
    policy_name = f"{app_name}-policy"
    secret_name = f"minio-{app_name}-credentials"
    
    typer.echo(f"Removendo usuário MinIO '{username}'...")
    
    try:
        root_user, root_password = _get_minio_root_credentials(ctx)
        _setup_mc_alias(ctx, root_user, root_password)
    except RuntimeError as e:
        typer.secho(f"  ✗ {e}", fg=typer.colors.RED)
        return False
    
    # Remove associação de política
    run_cmd(
        [
            "kubectl", "-n", "minio", "exec", "minio-0", "--",
            "mc", "admin", "policy", "detach", "local", policy_name, "--user", username,
        ],
        ctx,
        check=False,
    )
    
    # Remove usuário
    result = run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "admin", "user", "remove", "local", username],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.secho(f"  ✓ Usuário '{username}' removido.", fg=typer.colors.GREEN)
    
    # Remove política
    run_cmd(
        ["kubectl", "-n", "minio", "exec", "minio-0", "--", "mc", "admin", "policy", "remove", "local", policy_name],
        ctx,
        check=False,
    )
    
    # Remove secret K8s
    run_cmd(
        ["kubectl", "-n", app_name, "delete", "secret", secret_name, "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    return True
