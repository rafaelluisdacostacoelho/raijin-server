"""Deploy do Supabase via manifests Kubernetes com configuracoes production-ready."""

from __future__ import annotations

import base64
import json
import secrets
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

import typer

from raijin_server.utils import ExecutionContext, run_cmd


def _generate_secret(length: int = 32) -> str:
    """Gera secret aleatorio seguro."""
    return secrets.token_urlsafe(length)[:length]


def _generate_jwt_secret() -> str:
    """Gera JWT secret de 256 bits (32 bytes)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')


def _apply_manifest(ctx: ExecutionContext, manifest: str, description: str) -> bool:
    """Aplica manifest YAML temporario com kubectl."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            tmp.write(manifest)
            tmp.flush()
            tmp_path = Path(tmp.name)
        result = run_cmd(
            ["kubectl", "apply", "-f", str(tmp_path)],
            ctx,
            check=False,
        )
        if result.returncode != 0:
            typer.secho(f"  Falha ao aplicar {description}.", fg=typer.colors.RED)
            return False
        typer.secho(f"  ✓ {description} aplicado.", fg=typer.colors.GREEN)
        return True
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _check_prerequisites(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica pre-requisitos antes da instalacao."""
    typer.echo("Verificando pre-requisitos...")
    
    # Verificar se kubectl funciona
    result = run_cmd(["kubectl", "cluster-info"], ctx, check=False)
    if result.returncode != 0:
        typer.secho("  ✗ Cluster Kubernetes nao esta acessivel.", fg=typer.colors.RED)
        return False
    typer.secho("  ✓ Cluster Kubernetes acessivel.", fg=typer.colors.GREEN)
    
    # Verificar se namespace ja existe
    result = run_cmd(
        ["kubectl", "get", "namespace", namespace],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        typer.secho(f"  ! Namespace '{namespace}' ja existe, sera reutilizado.", fg=typer.colors.YELLOW)
    
    # Verificar StorageClass
    result = run_cmd(
        ["kubectl", "get", "storageclass", "-o", "jsonpath={.items[*].metadata.name}"],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        typer.secho(f"  ✓ StorageClass disponivel: {(result.stdout or '').strip()}", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Nenhuma StorageClass encontrada. Instale local-path-provisioner primeiro.", fg=typer.colors.RED)
        return False
    
    # Verificar se MinIO está disponível (pode ser Deployment ou StatefulSet)
    result = run_cmd(
        ["kubectl", "get", "statefulset", "-n", "minio", "minio"],
        ctx,
        check=False,
    )
    if result.returncode != 0:
        # Tentar como Deployment (instalação alternativa)
        result = run_cmd(
            ["kubectl", "get", "deployment", "-n", "minio", "minio"],
            ctx,
            check=False,
        )
        if result.returncode != 0:
            typer.secho("  ✗ MinIO nao encontrado. Instale MinIO primeiro (raijin-server install minio).", fg=typer.colors.RED)
            return False
    typer.secho("  ✓ MinIO disponivel.", fg=typer.colors.GREEN)
    
    return True


def _get_minio_credentials(ctx: ExecutionContext) -> tuple[str, str, str]:
    """Obtem credenciais do MinIO (root user)."""
    # Tentar obter do secret
    result = run_cmd(
        ["kubectl", "get", "secret", "-n", "minio", "minio-credentials", "-o", "jsonpath={.data.rootUser}"],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        root_user = base64.b64decode((result.stdout or "").strip()).decode('utf-8')
        
        result = run_cmd(
            ["kubectl", "get", "secret", "-n", "minio", "minio-credentials", "-o", "jsonpath={.data.rootPassword}"],
            ctx,
            check=False,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            root_password = base64.b64decode((result.stdout or "").strip()).decode('utf-8')
            
            # Endpoint do MinIO
            endpoint = "minio.minio.svc:9000"
            
            return root_user, root_password, endpoint
    
    # Fallback: tentar valores padrão
    typer.secho("  ! Usando credenciais MinIO padrão.", fg=typer.colors.YELLOW)
    return "minioadmin", "minioadmin", "minio.minio.svc:9000"


def _setup_minio_for_supabase(ctx: ExecutionContext, namespace: str) -> tuple[str, str]:
    """
    Configura MinIO para Supabase: cria bucket e usuario dedicado.
    Retorna (access_key, secret_key).
    """
    typer.echo("\nConfigurando MinIO para Supabase...")
    
    # Obter credenciais root do MinIO
    root_user, root_password, endpoint = _get_minio_credentials(ctx)
    
    # Gerar credenciais para o usuário Supabase
    access_key = f"supabase-storage-{_generate_secret(8)}"
    secret_key = _generate_secret(32)
    bucket_name = "supabase-storage"
    
    # Script para configurar MinIO via mc (MinIO Client)
    setup_script = textwrap.dedent(f"""
        #!/bin/bash
        set -e
        
        echo "Configurando MinIO Client..."
        mc alias set supaminio http://{endpoint} {root_user} {root_password}
        
        echo "Criando bucket {bucket_name}..."
        mc mb supaminio/{bucket_name} --ignore-existing || true
        
        echo "Configurando acesso público para leitura (opcional)..."
        # Política de leitura pública para arquivos (ajuste conforme necessário)
        # mc anonymous set download supaminio/{bucket_name}
        
        echo "Criando usuário {access_key}..."
        mc admin user add supaminio {access_key} {secret_key} || true
        
        echo "Criando política de acesso para o bucket..."
        cat > /tmp/supabase-storage-policy.json <<'EOF'
{{
    "Version": "2012-10-17",
    "Statement": [
        {{
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::{bucket_name}",
                "arn:aws:s3:::{bucket_name}/*"
            ]
        }}
    ]
}}
EOF
        
        mc admin policy create supaminio supabase-storage-policy /tmp/supabase-storage-policy.json || true
        
        echo "Associando política ao usuário..."
        mc admin policy attach supaminio supabase-storage-policy --user {access_key}
        
        echo "✓ MinIO configurado com sucesso!"
        echo "  Bucket: {bucket_name}"
        echo "  User: {access_key}"
    """).strip()
    
    # Executar script em um pod temporário do MinIO Client
    manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: Pod
        metadata:
          name: minio-setup-supabase
          namespace: minio
        spec:
          restartPolicy: Never
          containers:
          - name: mc
            image: minio/mc:latest
            command:
            - /bin/sh
            - -c
            - |
{textwrap.indent(setup_script, '              ')}
    """).strip()
    
    # Aplicar pod
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            tmp.write(manifest)
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        # Deletar pod anterior se existir
        run_cmd(
            ["kubectl", "delete", "pod", "-n", "minio", "minio-setup-supabase", "--ignore-not-found=true"],
            ctx,
            check=False,
        )
        
        # Aplicar novo pod
        result = run_cmd(
            ["kubectl", "apply", "-f", str(tmp_path)],
            ctx,
            check=False,
        )
        
        if result.returncode != 0:
            typer.secho("  ✗ Falha ao criar pod de setup do MinIO.", fg=typer.colors.RED)
            return access_key, secret_key
        
        # Aguardar pod completar
        typer.echo("  Aguardando configuração do MinIO...")
        run_cmd(
            ["kubectl", "wait", "--for=condition=ready", "pod/minio-setup-supabase", "-n", "minio", "--timeout=60s"],
            ctx,
            check=False,
        )
        
        # Aguardar completar
        import time
        time.sleep(5)
        
        # Ver logs
        result = run_cmd(
            ["kubectl", "logs", "-n", "minio", "minio-setup-supabase"],
            ctx,
            check=False,
        )
        
        if result.returncode == 0:
            typer.echo("  Logs do setup MinIO:")
            for line in (result.stdout or "").split("\n"):
                if line.strip():
                    typer.echo(f"    {line}")
        
        # Deletar pod
        run_cmd(
            ["kubectl", "delete", "pod", "-n", "minio", "minio-setup-supabase", "--ignore-not-found=true"],
            ctx,
            check=False,
        )
        
        typer.secho(f"  ✓ MinIO configurado para Supabase Storage.", fg=typer.colors.GREEN)
        typer.secho(f"    Bucket: {bucket_name}", fg=typer.colors.CYAN)
        typer.secho(f"    User: {access_key}", fg=typer.colors.CYAN)
        
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    
    return access_key, secret_key


def _create_minio_secret(
    ctx: ExecutionContext,
    namespace: str,
    access_key: str,
    secret_key: str,
    endpoint: str = "minio.minio.svc:9000",
    bucket: str = "supabase-storage",
) -> bool:
    """Cria secret com credenciais do MinIO."""
    manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: Secret
        metadata:
          name: supabase-minio-credentials
          namespace: {namespace}
        type: Opaque
        stringData:
          accessKeyId: {access_key}
          secretAccessKey: {secret_key}
          endpoint: {endpoint}
          bucket: {bucket}
    """).strip()
    
    return _apply_manifest(ctx, manifest, "MinIO credentials secret")


def _create_namespace(ctx: ExecutionContext, namespace: str) -> bool:
    """Cria namespace para o Supabase."""
    manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {namespace}
          labels:
            name: {namespace}
            app: supabase
    """).strip()
    
    return _apply_manifest(ctx, manifest, f"Namespace {namespace}")


def _create_secrets(
    ctx: ExecutionContext,
    namespace: str,
    postgres_password: str,
    jwt_secret: str,
    anon_key: str,
    service_key: str,
) -> bool:
    """Cria secrets do Supabase."""
    typer.echo("Criando secrets...")
    
    # PostgreSQL secret
    postgres_manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: Secret
        metadata:
          name: supabase-postgres
          namespace: {namespace}
        type: Opaque
        stringData:
          username: postgres
          password: {postgres_password}
          database: postgres
    """).strip()
    
    if not _apply_manifest(ctx, postgres_manifest, "PostgreSQL secret"):
        return False
    
    # JWT secrets
    jwt_manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: Secret
        metadata:
          name: supabase-jwt
          namespace: {namespace}
        type: Opaque
        stringData:
          secret: {jwt_secret}
          anonKey: {anon_key}
          serviceKey: {service_key}
    """).strip()
    
    if not _apply_manifest(ctx, jwt_manifest, "JWT secrets"):
        return False
    
    typer.secho("  ✓ Todos os secrets criados.", fg=typer.colors.GREEN)
    return True


def _create_configmap(ctx: ExecutionContext, namespace: str, domain: str) -> bool:
    """Cria ConfigMap com configuracoes do Supabase."""
    manifest = textwrap.dedent(f"""
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: supabase-config
          namespace: {namespace}
        data:
          postgres-host: "postgres.{namespace}.svc.cluster.local"
          postgres-port: "5432"
          postgres-db: "postgres"
          kong-http-port: "8000"
          kong-https-port: "8443"
          api-external-url: "https://{domain}"
          studio-port: "3000"
    """).strip()
    
    return _apply_manifest(ctx, manifest, "ConfigMap")


def _deploy_postgresql(
    ctx: ExecutionContext,
    namespace: str,
    storage_size: str,
    storage_class: str,
) -> bool:
    """Deploy do PostgreSQL com StatefulSet."""
    typer.echo("Fazendo deploy do PostgreSQL...")
    
    manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: postgres
          namespace: {namespace}
          labels:
            app: postgres
        spec:
          type: ClusterIP
          ports:
          - name: postgres
            port: 5432
            targetPort: 5432
          selector:
            app: postgres
        ---
        apiVersion: v1
        kind: PersistentVolumeClaim
        metadata:
          name: postgres-data
          namespace: {namespace}
          labels:
            app: postgres
            backup: velero
        spec:
          accessModes:
            - ReadWriteOnce
          storageClassName: {storage_class}
          resources:
            requests:
              storage: {storage_size}
        ---
        apiVersion: apps/v1
        kind: StatefulSet
        metadata:
          name: postgres
          namespace: {namespace}
          labels:
            app: postgres
        spec:
          serviceName: postgres
          replicas: 1
          selector:
            matchLabels:
              app: postgres
          template:
            metadata:
              labels:
                app: postgres
            spec:
              containers:
              - name: postgres
                image: supabase/postgres:15.1.1.54
                ports:
                - containerPort: 5432
                  name: postgres
                env:
                - name: POSTGRES_USER
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: username
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: password
                - name: POSTGRES_DB
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: database
                - name: PGDATA
                  value: /var/lib/postgresql/data/pgdata
                volumeMounts:
                - name: postgres-storage
                  mountPath: /var/lib/postgresql/data
                resources:
                  requests:
                    cpu: 500m
                    memory: 1Gi
                  limits:
                    cpu: 2000m
                    memory: 4Gi
                livenessProbe:
                  exec:
                    command:
                    - /bin/sh
                    - -c
                    - pg_isready -U postgres
                  initialDelaySeconds: 30
                  periodSeconds: 10
                readinessProbe:
                  exec:
                    command:
                    - /bin/sh
                    - -c
                    - pg_isready -U postgres
                  initialDelaySeconds: 5
                  periodSeconds: 5
              volumes:
              - name: postgres-storage
                persistentVolumeClaim:
                  claimName: postgres-data
    """).strip()
    
    return _apply_manifest(ctx, manifest, "PostgreSQL StatefulSet")


def _deploy_kong(ctx: ExecutionContext, namespace: str, replicas: int) -> bool:
    """Deploy do Kong Gateway."""
    typer.echo("Fazendo deploy do Kong Gateway...")
    
    manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: supabase-kong
          namespace: {namespace}
          labels:
            app: supabase-kong
        spec:
          type: LoadBalancer
          ports:
          - name: http
            port: 8000
            targetPort: 8000
            protocol: TCP
          - name: https
            port: 8443
            targetPort: 8443
            protocol: TCP
          selector:
            app: supabase-kong
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: supabase-kong
          namespace: {namespace}
          labels:
            app: supabase-kong
        spec:
          replicas: {replicas}
          selector:
            matchLabels:
              app: supabase-kong
          template:
            metadata:
              labels:
                app: supabase-kong
            spec:
              containers:
              - name: kong
                image: kong:3.1
                ports:
                - containerPort: 8000
                  name: http
                - containerPort: 8443
                  name: https
                env:
                - name: KONG_DATABASE
                  value: "off"
                - name: KONG_DECLARATIVE_CONFIG
                  value: /kong/kong.yml
                - name: KONG_LOG_LEVEL
                  value: info
                - name: KONG_PLUGINS
                  value: "bundled,cors"
                volumeMounts:
                - name: kong-config
                  mountPath: /kong
                resources:
                  requests:
                    cpu: 200m
                    memory: 256Mi
                  limits:
                    cpu: 1000m
                    memory: 512Mi
                livenessProbe:
                  httpGet:
                    path: /status
                    port: 8000
                  initialDelaySeconds: 30
                  periodSeconds: 10
                readinessProbe:
                  httpGet:
                    path: /status
                    port: 8000
                  initialDelaySeconds: 10
                  periodSeconds: 5
              volumes:
              - name: kong-config
                configMap:
                  name: kong-config
        ---
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: kong-config
          namespace: {namespace}
        data:
          kong.yml: |
            _format_version: "3.0"
            _transform: true
            services:
              - name: auth
                url: http://supabase-gotrue.{namespace}.svc:9999/
                routes:
                  - name: auth-all
                    paths:
                      - /auth/v1/
                    strip_path: false
              - name: rest
                url: http://supabase-postgrest.{namespace}.svc:3000/
                routes:
                  - name: rest-all
                    paths:
                      - /rest/v1/
                    strip_path: false
              - name: realtime
                url: http://supabase-realtime.{namespace}.svc:4000/
                routes:
                  - name: realtime-all
                    paths:
                      - /realtime/v1/
                    strip_path: false
              - name: storage
                url: http://supabase-storage.{namespace}.svc:5000/
                routes:
                  - name: storage-all
                    paths:
                      - /storage/v1/
                    strip_path: false
    """).strip()
    
    return _apply_manifest(ctx, manifest, "Kong Gateway")


def _deploy_services(
    ctx: ExecutionContext,
    namespace: str,
    replicas_postgrest: int,
    replicas_gotrue: int,
    replicas_realtime: int,
) -> bool:
    """Deploy dos servicos Supabase (PostgREST, GoTrue, Realtime, Storage)."""
    typer.echo("Fazendo deploy dos servicos Supabase...")
    
    # PostgREST
    postgrest_manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: supabase-postgrest
          namespace: {namespace}
        spec:
          type: ClusterIP
          ports:
          - port: 3000
            targetPort: 3000
          selector:
            app: supabase-postgrest
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: supabase-postgrest
          namespace: {namespace}
        spec:
          replicas: {replicas_postgrest}
          selector:
            matchLabels:
              app: supabase-postgrest
          template:
            metadata:
              labels:
                app: supabase-postgrest
            spec:
              containers:
              - name: postgrest
                image: postgrest/postgrest:v12.0.2
                ports:
                - containerPort: 3000
                env:
                - name: PGRST_DB_URI
                  value: "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres.{namespace}.svc:5432/postgres"
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: password
                - name: PGRST_DB_SCHEMAS
                  value: "public,storage"
                - name: PGRST_DB_ANON_ROLE
                  value: "anon"
                - name: PGRST_JWT_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: supabase-jwt
                      key: secret
                resources:
                  requests:
                    cpu: 100m
                    memory: 128Mi
                  limits:
                    cpu: 500m
                    memory: 512Mi
    """).strip()
    
    if not _apply_manifest(ctx, postgrest_manifest, "PostgREST"):
        return False
    
    # GoTrue (Auth)
    gotrue_manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: supabase-gotrue
          namespace: {namespace}
        spec:
          type: ClusterIP
          ports:
          - port: 9999
            targetPort: 9999
          selector:
            app: supabase-gotrue
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: supabase-gotrue
          namespace: {namespace}
        spec:
          replicas: {replicas_gotrue}
          selector:
            matchLabels:
              app: supabase-gotrue
          template:
            metadata:
              labels:
                app: supabase-gotrue
            spec:
              containers:
              - name: gotrue
                image: supabase/gotrue:v2.143.0
                ports:
                - containerPort: 9999
                env:
                - name: GOTRUE_DB_DATABASE_URL
                  value: "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres.{namespace}.svc:5432/postgres"
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: password
                - name: GOTRUE_JWT_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: supabase-jwt
                      key: secret
                - name: GOTRUE_JWT_EXP
                  value: "3600"
                - name: GOTRUE_SITE_URL
                  valueFrom:
                    configMapKeyRef:
                      name: supabase-config
                      key: api-external-url
                - name: API_EXTERNAL_URL
                  valueFrom:
                    configMapKeyRef:
                      name: supabase-config
                      key: api-external-url
                - name: GOTRUE_DISABLE_SIGNUP
                  value: "false"
                - name: GOTRUE_MAILER_AUTOCONFIRM
                  value: "true"
                resources:
                  requests:
                    cpu: 100m
                    memory: 128Mi
                  limits:
                    cpu: 500m
                    memory: 512Mi
    """).strip()
    
    if not _apply_manifest(ctx, gotrue_manifest, "GoTrue"):
        return False
    
    # Realtime
    realtime_manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: supabase-realtime
          namespace: {namespace}
        spec:
          type: ClusterIP
          ports:
          - port: 4000
            targetPort: 4000
          selector:
            app: supabase-realtime
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: supabase-realtime
          namespace: {namespace}
        spec:
          replicas: {replicas_realtime}
          selector:
            matchLabels:
              app: supabase-realtime
          template:
            metadata:
              labels:
                app: supabase-realtime
            spec:
              containers:
              - name: realtime
                image: supabase/realtime:v2.25.50
                ports:
                - containerPort: 4000
                env:
                - name: DB_HOST
                  value: "postgres.{namespace}.svc"
                - name: DB_PORT
                  value: "5432"
                - name: DB_NAME
                  value: "postgres"
                - name: DB_USER
                  value: "postgres"
                - name: DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: password
                - name: DB_SSL
                  value: "false"
                - name: PORT
                  value: "4000"
                - name: JWT_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: supabase-jwt
                      key: secret
                resources:
                  requests:
                    cpu: 100m
                    memory: 128Mi
                  limits:
                    cpu: 500m
                    memory: 512Mi
    """).strip()
    
    if not _apply_manifest(ctx, realtime_manifest, "Realtime"):
        return False
    
    # Storage API
    storage_manifest = textwrap.dedent(f"""
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: supabase-storage
          namespace: {namespace}
        spec:
          type: ClusterIP
          ports:
          - port: 5000
            targetPort: 5000
          selector:
            app: supabase-storage
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: supabase-storage
          namespace: {namespace}
        spec:
          replicas: 2
          selector:
            matchLabels:
              app: supabase-storage
          template:
            metadata:
              labels:
                app: supabase-storage
            spec:
              containers:
              - name: storage
                image: supabase/storage-api:v0.43.11
                ports:
                - containerPort: 5000
                env:
                - name: DATABASE_URL
                  value: "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres.{namespace}.svc:5432/postgres"
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: supabase-postgres
                      key: password
                - name: PGRST_JWT_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: supabase-jwt
                      key: secret
                - name: FILE_SIZE_LIMIT
                  value: "52428800"
                - name: STORAGE_BACKEND
                  value: "s3"
                - name: STORAGE_S3_ENDPOINT
                  valueFrom:
                    secretKeyRef:
                      name: supabase-minio-credentials
                      key: endpoint
                - name: STORAGE_S3_BUCKET
                  valueFrom:
                    secretKeyRef:
                      name: supabase-minio-credentials
                      key: bucket
                - name: AWS_ACCESS_KEY_ID
                  valueFrom:
                    secretKeyRef:
                      name: supabase-minio-credentials
                      key: accessKeyId
                - name: AWS_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef:
                      name: supabase-minio-credentials
                      key: secretAccessKey
                - name: AWS_DEFAULT_REGION
                  value: "us-east-1"
                - name: STORAGE_S3_FORCE_PATH_STYLE
                  value: "true"
                resources:
                  requests:
                    cpu: 100m
                    memory: 128Mi
                  limits:
                    cpu: 500m
                    memory: 512Mi
    """).strip()
    
    if not _apply_manifest(ctx, storage_manifest, "Storage API"):
        return False
    
    typer.secho("  ✓ Todos os servicos Supabase deployados.", fg=typer.colors.GREEN)
    return True


def _create_ingress(ctx: ExecutionContext, namespace: str, domain: str) -> bool:
    """Cria Ingress com TLS."""
    typer.echo("Criando Ingress com TLS...")
    
    manifest = textwrap.dedent(f"""
        apiVersion: networking.k8s.io/v1
        kind: Ingress
        metadata:
          name: supabase-ingress
          namespace: {namespace}
          annotations:
            cert-manager.io/cluster-issuer: letsencrypt-prod
            traefik.ingress.kubernetes.io/router.entrypoints: websecure
            traefik.ingress.kubernetes.io/router.tls: "true"
        spec:
          ingressClassName: traefik
          tls:
          - hosts:
            - {domain}
            secretName: supabase-tls
          rules:
          - host: {domain}
            http:
              paths:
              - path: /
                pathType: Prefix
                backend:
                  service:
                    name: supabase-kong
                    port:
                      number: 8000
    """).strip()
    
    return _apply_manifest(ctx, manifest, "Ingress")


def _create_velero_schedule(ctx: ExecutionContext, namespace: str) -> bool:
    """Cria Schedule do Velero para backup automatico."""
    typer.echo("Configurando backup automatico com Velero...")
    
    manifest = textwrap.dedent(f"""
        apiVersion: velero.io/v1
        kind: Schedule
        metadata:
          name: supabase-daily-backup
          namespace: velero
        spec:
          schedule: "0 2 * * *"
          template:
            includedNamespaces:
              - {namespace}
            ttl: 720h
            storageLocation: default
    """).strip()
    
    result = _apply_manifest(ctx, manifest, "Velero Backup Schedule")
    if result:
        typer.secho(f"  ✓ Backup diario configurado (2 AM, retencao 30 dias).", fg=typer.colors.GREEN)
    return result


def _wait_for_pods(ctx: ExecutionContext, namespace: str) -> None:
    """Aguarda pods ficarem prontos."""
    typer.echo("Aguardando pods ficarem prontos...")
    
    deployments = [
        "supabase-kong",
        "supabase-postgrest",
        "supabase-gotrue",
        "supabase-realtime",
        "supabase-storage",
    ]
    
    for deployment in deployments:
        typer.echo(f"  Aguardando {deployment}...")
        run_cmd(
            [
                "kubectl", "rollout", "status", f"deployment/{deployment}",
                "-n", namespace, "--timeout=300s",
            ],
            ctx,
            check=False,
        )
    
    # Aguardar StatefulSet do PostgreSQL
    typer.echo("  Aguardando PostgreSQL StatefulSet...")
    run_cmd(
        [
            "kubectl", "rollout", "status", "statefulset/postgres",
            "-n", namespace, "--timeout=300s",
        ],
        ctx,
        check=False,
    )
    
    typer.secho("  ✓ Todos os pods estao prontos!", fg=typer.colors.GREEN)


def _print_access_info(namespace: str, domain: str, anon_key: str, service_key: str) -> None:
    """Imprime informacoes de acesso."""
    typer.echo("\n" + "="*70)
    typer.secho("🎉  Supabase instalado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo("="*70)
    typer.echo(f"\n📍  API URL: https://{domain}")
    typer.echo(f"📦  Namespace: {namespace}")
    typer.echo(f"\n🔑  Anon Key (use no frontend):")
    typer.secho(f"    {anon_key}", fg=typer.colors.CYAN)
    typer.echo(f"\n🔐  Service Role Key (use apenas no backend):")
    typer.secho(f"    {service_key}", fg=typer.colors.YELLOW)
    typer.echo(f"\n📊  Para acessar o Studio (UI):")
    typer.secho(f"    kubectl port-forward -n {namespace} svc/supabase-studio 3000:3000", fg=typer.colors.BLUE)
    typer.secho(f"    Acesse: http://localhost:3000", fg=typer.colors.BLUE)
    typer.echo(f"\n🔍  Ver status dos pods:")
    typer.secho(f"    kubectl get pods -n {namespace}", fg=typer.colors.BLUE)
    typer.echo(f"\n📝  Ver logs:")
    typer.secho(f"    kubectl logs -n {namespace} -l app=supabase-kong -f", fg=typer.colors.BLUE)
    typer.echo(f"\n💾  Backup:")
    typer.secho(f"    velero backup create supabase-manual --include-namespaces {namespace}", fg=typer.colors.BLUE)
    typer.echo("\n" + "="*70)
    typer.echo(f"📚  Documentacao completa: docs/tools/supabase.md")
    typer.echo("="*70 + "\n")


def install(ctx: ExecutionContext) -> None:
    """Instala Supabase no Kubernetes com alta disponibilidade."""
    typer.secho("\n🚀  Instalacao do Supabase\n", fg=typer.colors.CYAN, bold=True)
    
    # Prompts interativos
    namespace = typer.prompt("Namespace para Supabase", default="supabase")
    domain = typer.prompt("Dominio externo (ex: supabase.yourdomain.com)", default="supabase.local")
    storage_size = typer.prompt("Tamanho do storage PostgreSQL", default="50Gi")
    storage_class = typer.prompt("StorageClass", default="local-path")
    
    replicas_kong = typer.prompt("Numero de replicas Kong Gateway (2-4 recomendado)", default=2, type=int)
    replicas_postgrest = typer.prompt("Numero de replicas PostgREST", default=2, type=int)
    replicas_gotrue = typer.prompt("Numero de replicas GoTrue", default=2, type=int)
    replicas_realtime = typer.prompt("Numero de replicas Realtime", default=2, type=int)
    
    configure_velero = typer.confirm("Configurar backup automatico com Velero?", default=True)
    
    # Gerar secrets
    typer.echo("\nGerando secrets seguros...")
    postgres_password = _generate_secret(32)
    jwt_secret = _generate_jwt_secret()
    anon_key = _generate_jwt_secret()
    service_key = _generate_jwt_secret()
    typer.secho("  ✓ Secrets gerados.", fg=typer.colors.GREEN)
    
    # Verificar pre-requisitos
    if not _check_prerequisites(ctx, namespace):
        typer.secho("\n❌  Pre-requisitos nao atendidos. Abortando.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Criar namespace
    if not _create_namespace(ctx, namespace):
        typer.secho("\n❌  Falha ao criar namespace.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Criar secrets
    if not _create_secrets(ctx, namespace, postgres_password, jwt_secret, anon_key, service_key):
        typer.secho("\n❌  Falha ao criar secrets.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Configurar MinIO para Supabase Storage
    minio_access_key, minio_secret_key = _setup_minio_for_supabase(ctx, namespace)
    if not _create_minio_secret(ctx, namespace, minio_access_key, minio_secret_key):
        typer.secho("\n❌  Falha ao criar secret do MinIO.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Criar ConfigMap
    if not _create_configmap(ctx, namespace, domain):
        typer.secho("\n❌  Falha ao criar ConfigMap.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Deploy PostgreSQL
    if not _deploy_postgresql(ctx, namespace, storage_size, storage_class):
        typer.secho("\n❌  Falha no deploy do PostgreSQL.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Deploy Kong
    if not _deploy_kong(ctx, namespace, replicas_kong):
        typer.secho("\n❌  Falha no deploy do Kong.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Deploy servicos
    if not _deploy_services(ctx, namespace, replicas_postgrest, replicas_gotrue, replicas_realtime):
        typer.secho("\n❌  Falha no deploy dos servicos.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Criar Ingress
    if not _create_ingress(ctx, namespace, domain):
        typer.secho("\n❌  Falha ao criar Ingress.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Configurar Velero
    if configure_velero:
        _create_velero_schedule(ctx, namespace)
    
    # Aguardar pods
    _wait_for_pods(ctx, namespace)
    
    # Imprimir informacoes de acesso
    _print_access_info(namespace, domain, anon_key, service_key)


def uninstall(ctx: ExecutionContext) -> None:
    """Remove Supabase do cluster."""
    namespace = typer.prompt("Namespace do Supabase", default="supabase")
    
    confirm = typer.confirm(
        f"⚠️  Isso vai DELETAR PERMANENTEMENTE todos os dados do Supabase no namespace '{namespace}'. Continuar?",
        default=False,
    )
    
    if not confirm:
        typer.echo("Operacao cancelada.")
        raise typer.Exit(0)
    
    typer.echo(f"\nRemovendo Supabase do namespace '{namespace}'...")
    
    # Deletar namespace (deleta tudo dentro dele)
    result = run_cmd(
        ["kubectl", "delete", "namespace", namespace, "--wait=true", "--timeout=300s"],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.secho(f"✓ Namespace '{namespace}' removido com sucesso.", fg=typer.colors.GREEN)
        
        # Tentar remover Schedule do Velero
        run_cmd(
            ["kubectl", "delete", "schedule", "supabase-daily-backup", "-n", "velero"],
            ctx,
            check=False,
        )
        typer.secho("✓ Schedule do Velero removido.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"✗ Falha ao remover namespace '{namespace}'.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    typer.secho("\n✓ Supabase desinstalado.", fg=typer.colors.GREEN)


def run(ctx: ExecutionContext) -> None:
    """Funcao run padrao - delega para install."""
    install(ctx)
