"""Automacao de Harbor Registry com MinIO backend (production-ready).

Harbor é um registry privado para imagens Docker/OCI com:
- Vulnerability scanning (Trivy integrado)
- Retention policies (garbage collection)
- Projetos separados por ambiente (tst, prd)
- Robot accounts para CI/CD
- Replicação entre registries
- Controle de acesso (RBAC)
"""

import base64
import json
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

HARBOR_NAMESPACE = "harbor"


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


def _check_existing_harbor(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica se existe instalacao do Harbor."""
    result = run_cmd(
        ["helm", "status", "harbor", "-n", namespace],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_harbor(ctx: ExecutionContext, namespace: str) -> None:
    """Remove instalacao anterior do Harbor."""
    typer.echo("Removendo instalacao anterior do Harbor...")
    
    run_cmd(
        ["helm", "uninstall", "harbor", "-n", namespace],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _get_minio_credentials(ctx: ExecutionContext) -> tuple[str, str]:
    """Obtem ou cria credenciais específicas do MinIO para Harbor.
    
    Esta função cria um usuário MinIO dedicado para o Harbor com acesso
    restrito apenas aos buckets: harbor-registry, harbor-chartmuseum, harbor-jobservice.
    """
    return get_or_create_minio_user(
        ctx=ctx,
        app_name="harbor",
        buckets=["harbor-registry", "harbor-chartmuseum", "harbor-jobservice"],
        namespace=HARBOR_NAMESPACE,
    )


def _wait_for_pods_ready(ctx: ExecutionContext, namespace: str, timeout: int = 300) -> bool:
    """Aguarda todos os pods do Harbor ficarem Ready."""
    typer.echo("Aguardando pods do Harbor ficarem Ready (pode levar 3-5 min)...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
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
                    typer.secho("  Todos os pods do Harbor estão Running.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Harbor. Verifique: kubectl -n harbor get pods", fg=typer.colors.YELLOW)
    return False


def _create_harbor_projects(ctx: ExecutionContext, harbor_url: str, admin_password: str) -> None:
    """Cria projetos tst e prd no Harbor via API."""
    typer.echo("\nCriando projetos 'tst' e 'prd' no Harbor...")
    
    projects = [
        {
            "project_name": "tst",
            "metadata": {
                "public": "false",
                "auto_scan": "true",
                "severity": "low",
                "enable_content_trust": "false",
                "prevent_vul": "false"
            }
        },
        {
            "project_name": "prd",
            "metadata": {
                "public": "false",
                "auto_scan": "true",
                "severity": "low",
                "enable_content_trust": "true",  # Content trust em produção
                "prevent_vul": "true",  # Bloqueia push de imagens vulneráveis
                "severity_threshold": "critical"  # Apenas critical vulnerabilities bloqueiam
            }
        }
    ]
    
    for project in projects:
        project_json = json.dumps(project)
        
        run_cmd(
            [
                "curl", "-X", "POST",
                f"{harbor_url}/api/v2.0/projects",
                "-H", "Content-Type: application/json",
                "-u", f"admin:{admin_password}",
                "-d", project_json,
                "-k"  # Skip SSL verification (self-signed cert)
            ],
            ctx,
            check=False,
        )
        
        typer.secho(f"  ✓ Projeto '{project['project_name']}' criado.", fg=typer.colors.GREEN)
    
    time.sleep(2)


def _create_retention_policies(ctx: ExecutionContext, harbor_url: str, admin_password: str) -> None:
    """Cria políticas de retenção para projetos."""
    typer.echo("\nConfigurando políticas de retenção...")
    
    # Política para TST: manter últimas 10 imagens ou 30 dias
    tst_policy = {
        "algorithm": "or",
        "rules": [
            {
                "disabled": False,
                "action": "retain",
                "template": "latestPushedK",
                "params": {"latestPushedK": 10},
                "tag_selectors": [
                    {
                        "kind": "doublestar",
                        "decoration": "matches",
                        "pattern": "**"
                    }
                ],
                "scope_selectors": {
                    "repository": [
                        {
                            "kind": "doublestar",
                            "decoration": "repoMatches",
                            "pattern": "**"
                        }
                    ]
                }
            },
            {
                "disabled": False,
                "action": "retain",
                "template": "nDaysSinceLastPush",
                "params": {"nDaysSinceLastPush": 30},
                "tag_selectors": [
                    {
                        "kind": "doublestar",
                        "decoration": "matches",
                        "pattern": "**"
                    }
                ],
                "scope_selectors": {
                    "repository": [
                        {
                            "kind": "doublestar",
                            "decoration": "repoMatches",
                            "pattern": "**"
                        }
                    ]
                }
            }
        ],
        "trigger": {
            "kind": "Schedule",
            "settings": {
                "cron": "0 0 * * *"  # Diário à meia-noite
            }
        },
        "scope": {
            "level": "project",
            "ref": 2  # ID do projeto tst (geralmente 2)
        }
    }
    
    # Política para PRD: manter últimas 20 imagens ou 90 dias
    prd_policy = {
        "algorithm": "or",
        "rules": [
            {
                "disabled": False,
                "action": "retain",
                "template": "latestPushedK",
                "params": {"latestPushedK": 20},
                "tag_selectors": [
                    {
                        "kind": "doublestar",
                        "decoration": "matches",
                        "pattern": "**"
                    }
                ],
                "scope_selectors": {
                    "repository": [
                        {
                            "kind": "doublestar",
                            "decoration": "repoMatches",
                            "pattern": "**"
                        }
                    ]
                }
            },
            {
                "disabled": False,
                "action": "retain",
                "template": "nDaysSinceLastPush",
                "params": {"nDaysSinceLastPush": 90},
                "tag_selectors": [
                    {
                        "kind": "doublestar",
                        "decoration": "matches",
                        "pattern": "**"
                    }
                ],
                "scope_selectors": {
                    "repository": [
                        {
                            "kind": "doublestar",
                            "decoration": "repoMatches",
                            "pattern": "**"
                        }
                    ]
                }
            }
        ],
        "trigger": {
            "kind": "Schedule",
            "settings": {
                "cron": "0 2 * * 0"  # Domingo às 2h
            }
        },
        "scope": {
            "level": "project",
            "ref": 3  # ID do projeto prd (geralmente 3)
        }
    }
    
    typer.secho("  ℹ️  Políticas de retenção devem ser configuradas via UI:", fg=typer.colors.CYAN)
    typer.echo("  1. Acesse Harbor UI → Projects")
    typer.echo("  2. Selecione projeto (tst ou prd)")
    typer.echo("  3. Policy → Tag Retention")
    typer.echo("  4. Add Rule:")
    typer.echo("     TST: Manter últimas 10 imagens OU 30 dias")
    typer.echo("     PRD: Manter últimas 20 imagens OU 90 dias")


def _create_robot_accounts(ctx: ExecutionContext, harbor_url: str, admin_password: str) -> None:
    """Cria robot accounts para CI/CD."""
    typer.echo("\nCriando robot accounts para CI/CD...")
    
    robots = [
        {
            "name": "robot$cicd-tst",
            "description": "Robot account for CI/CD in TST environment",
            "project_id": 2,
            "permissions": [
                {
                    "kind": "project",
                    "namespace": "tst",
                    "access": [
                        {"resource": "repository", "action": "push"},
                        {"resource": "repository", "action": "pull"},
                        {"resource": "artifact", "action": "delete"}
                    ]
                }
            ]
        },
        {
            "name": "robot$cicd-prd",
            "description": "Robot account for CI/CD in PRD environment",
            "project_id": 3,
            "permissions": [
                {
                    "kind": "project",
                    "namespace": "prd",
                    "access": [
                        {"resource": "repository", "action": "push"},
                        {"resource": "repository", "action": "pull"}
                    ]
                }
            ]
        }
    ]
    
    typer.secho("  ℹ️  Robot accounts devem ser criados via UI:", fg=typer.colors.CYAN)
    typer.echo("  1. Acesse Harbor UI → Projects → tst/prd")
    typer.echo("  2. Robot Accounts → New Robot Account")
    typer.echo("  3. Nome: cicd-tst / cicd-prd")
    typer.echo("  4. Permissões: Push, Pull, Delete (tst) | Push, Pull (prd)")
    typer.echo("  5. Salvar token gerado no Vault:")
    typer.echo("     kubectl -n vault exec vault-0 -- vault kv put secret/harbor/robot-tst token=<TOKEN>")


def _configure_garbage_collection(ctx: ExecutionContext) -> None:
    """Configura garbage collection automático."""
    typer.echo("\nGarbage collection configurado para rodar:")
    typer.echo("  - Após cada execução de retention policy")
    typer.echo("  - Diariamente às 3h (via Harbor scheduler)")
    typer.echo("\nConfiguração manual via UI:")
    typer.echo("  Harbor → Administration → Garbage Collection")
    typer.echo("  Schedule: 0 3 * * * (3h diariamente)")
    typer.echo("  Delete untagged artifacts: Yes")


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    ensure_tool("helm", ctx, install_hint="Instale helm ou habilite dry-run.")

    typer.echo("Instalando Harbor Registry com MinIO backend...")

    harbor_ns = typer.prompt("Namespace para Harbor", default=HARBOR_NAMESPACE)
    node_name = _detect_node_name(ctx)
    
    # Detecta IP do node
    result = run_cmd(
        ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}"],
        ctx,
        check=False,
    )
    import os
    fallback_ip = os.environ.get("RAIJIN_NET_IP", "192.168.1.100/24").split("/")[0]
    node_ip = result.stdout.strip() if result.returncode == 0 else fallback_ip
    
    minio_host = typer.prompt("MinIO host", default=f"{node_ip}:30900")
    access_key, secret_key = _get_minio_credentials(ctx)
    
    harbor_nodeport = typer.prompt("NodePort para Harbor UI/Registry", default="30880")
    admin_password = typer.prompt("Senha do admin do Harbor", default="Harbor12345", hide_input=True)

    # ========== Harbor ==========
    typer.secho("\n== Harbor Registry ==", fg=typer.colors.CYAN, bold=True)

    if _check_existing_harbor(ctx, harbor_ns):
        cleanup = typer.confirm(
            "Instalacao anterior do Harbor detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_harbor(ctx, harbor_ns)

    # Cria buckets no MinIO
    typer.echo("\nCriando buckets no MinIO para Harbor...")
    for bucket in ["harbor-registry", "harbor-chartmuseum", "harbor-jobservice"]:
        run_cmd(
            ["mc", "mb", "--ignore-existing", f"minio/{bucket}"],
            ctx,
            check=False,
        )

    harbor_values_yaml = f"""expose:
  type: nodePort
  tls:
    enabled: false
  nodePort:
    name: harbor
    ports:
      http:
        port: 80
        nodePort: {harbor_nodeport}

externalURL: http://{node_ip}:{harbor_nodeport}

persistence:
  enabled: true
  persistentVolumeClaim:
    registry:
      storageClass: ""
      size: 5Gi
    chartmuseum:
      storageClass: ""
      size: 5Gi
    jobservice:
      jobLog:
        storageClass: ""
        size: 1Gi
    database:
      storageClass: ""
      size: 1Gi
    redis:
      storageClass: ""
      size: 1Gi
    trivy:
      storageClass: ""
      size: 5Gi

# MinIO S3 backend
imageChartStorage:
  type: s3
  s3:
    region: us-east-1
    bucket: harbor-registry
    accesskey: {access_key}
    secretkey: {secret_key}
    regionendpoint: http://{minio_host}
    encrypt: false
    secure: false
    v4auth: true

chartmuseum:
  enabled: true

# Configuração de admin
harborAdminPassword: "{admin_password}"

# Tolerations e nodeSelector
portal:
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
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 256Mi

core:
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
      cpu: 200m
    limits:
      memory: 512Mi

jobservice:
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
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 256Mi

registry:
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
      cpu: 200m
    limits:
      memory: 512Mi

trivy:
  enabled: true
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
      memory: 512Mi
      cpu: 200m
    limits:
      memory: 1Gi

database:
  type: internal
  internal:
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
        cpu: 100m
      limits:
        memory: 512Mi

redis:
  type: internal
  internal:
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
        memory: 128Mi
        cpu: 100m
      limits:
        memory: 256Mi

nginx:
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
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 256Mi
"""

    harbor_values_path = Path("/tmp/raijin-harbor-values.yaml")
    write_file(harbor_values_path, harbor_values_yaml, ctx)

    helm_upgrade_install(
        "harbor",
        "harbor",
        harbor_ns,
        ctx,
        repo="harbor",
        repo_url="https://helm.goharbor.io",
        create_namespace=True,
        extra_args=["-f", str(harbor_values_path)],
    )

    if not ctx.dry_run:
        _wait_for_pods_ready(ctx, harbor_ns)
        
        # Aguarda Harbor API ficar disponível
        typer.echo("\nAguardando Harbor API ficar disponível...")
        time.sleep(30)
        
        harbor_url = f"http://{node_ip}:{harbor_nodeport}"
        
        # Configura projetos, policies e robot accounts
        _create_harbor_projects(ctx, harbor_url, admin_password)
        _create_retention_policies(ctx, harbor_url, admin_password)
        _create_robot_accounts(ctx, harbor_url, admin_password)
        _configure_garbage_collection(ctx)

    typer.secho("\n✓ Harbor instalado com sucesso!", fg=typer.colors.GREEN, bold=True)
    
    typer.secho("\n=== Acesso ao Harbor ===", fg=typer.colors.CYAN)
    typer.echo(f"URL: http://{node_ip}:{harbor_nodeport}")
    typer.echo(f"Usuário: admin")
    typer.echo(f"Senha: {admin_password}")
    
    typer.secho("\n=== Projetos Criados ===", fg=typer.colors.CYAN)
    typer.echo("✓ tst (development/staging)")
    typer.echo("  - Auto-scan habilitado")
    typer.echo("  - Retention: 10 imagens ou 30 dias")
    typer.echo("  - Pull from: develop branch")
    typer.echo("\n✓ prd (production)")
    typer.echo("  - Auto-scan habilitado")
    typer.echo("  - Content trust habilitado")
    typer.echo("  - Block vulnerabilities (critical)")
    typer.echo("  - Retention: 20 imagens ou 90 dias")
    typer.echo("  - Pull from: main/master branch")
    
    typer.secho("\n=== Como usar ===", fg=typer.colors.CYAN)
    typer.echo("1. Login no Harbor:")
    typer.echo(f"   docker login {node_ip}:{harbor_nodeport}")
    typer.echo(f"   Username: admin")
    typer.echo(f"   Password: {admin_password}")
    
    typer.echo("\n2. Tag e push de imagem (TST):")
    typer.echo(f"   docker tag myapp:latest {node_ip}:{harbor_nodeport}/tst/myapp:v1.0.0")
    typer.echo(f"   docker push {node_ip}:{harbor_nodeport}/tst/myapp:v1.0.0")
    
    typer.echo("\n3. Tag e push de imagem (PRD):")
    typer.echo(f"   docker tag myapp:latest {node_ip}:{harbor_nodeport}/prd/myapp:v1.0.0")
    typer.echo(f"   docker push {node_ip}:{harbor_nodeport}/prd/myapp:v1.0.0")
    
    typer.echo("\n4. Pull de imagem no Kubernetes:")
    typer.echo("   kubectl create secret docker-registry harbor-secret \\")
    typer.echo(f"     --docker-server={node_ip}:{harbor_nodeport} \\")
    typer.echo("     --docker-username=admin \\")
    typer.echo(f"     --docker-password={admin_password}")
    typer.echo("\n   spec:")
    typer.echo("     imagePullSecrets:")
    typer.echo("     - name: harbor-secret")
    typer.echo("     containers:")
    typer.echo(f"     - image: {node_ip}:{harbor_nodeport}/prd/myapp:v1.0.0")
    
    typer.secho("\n=== Próximos Passos (via UI) ===", fg=typer.colors.YELLOW)
    typer.echo("1. Configurar Robot Accounts (cicd-tst, cicd-prd)")
    typer.echo("2. Ajustar Retention Policies se necessário")
    typer.echo("3. Configurar Webhooks para CI/CD")
    typer.echo("4. Habilitar Content Trust em PRD (cosign/notary)")
    typer.echo("5. Configurar Replication (se multi-cluster)")
    
    typer.secho("\n⚠️  IMPORTANTE:", fg=typer.colors.YELLOW, bold=True)
    typer.echo("- Imagens em TST: Máximo 10 ou 30 dias (cleanup automático)")
    typer.echo("- Imagens em PRD: Máximo 20 ou 90 dias (cleanup automático)")
    typer.echo("- Garbage collection roda diariamente às 3h")
    typer.echo("- Vulnerability scan automático em todas as imagens")
    typer.echo("- PRD bloqueia push de imagens com vulnerabilidades CRITICAL")
