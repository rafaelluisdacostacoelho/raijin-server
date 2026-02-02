"""Instalacao do Argo CD + Argo Workflows (GitOps CI/CD 100% opensource)."""

import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd, write_file


ARGOCD_NS = "argocd"
ARGO_WORKFLOWS_NS = "argo"


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


def _check_existing_argocd(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Argo CD."""
    result = run_cmd(
        ["helm", "status", "argocd", "-n", ARGOCD_NS],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_existing_workflows(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Argo Workflows."""
    result = run_cmd(
        ["helm", "status", "argo-workflows", "-n", ARGO_WORKFLOWS_NS],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_argocd(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Argo CD."""
    typer.echo("Removendo instalacao anterior do Argo CD...")
    run_cmd(["helm", "uninstall", "argocd", "-n", ARGOCD_NS], ctx, check=False)
    time.sleep(5)


def _uninstall_workflows(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Argo Workflows."""
    typer.echo("Removendo instalacao anterior do Argo Workflows...")
    run_cmd(["helm", "uninstall", "argo-workflows", "-n", ARGO_WORKFLOWS_NS], ctx, check=False)
    time.sleep(5)


def _wait_for_pods_ready(ctx: ExecutionContext, namespace: str, label: str, timeout: int = 300) -> bool:
    """Aguarda pods ficarem Ready."""
    typer.echo(f"Aguardando pods no namespace {namespace}...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
                "-l", label,
                "-o", "jsonpath={range .items[*]}{.status.phase} {end}",
            ],
            ctx,
            check=False,
        )

        if result.returncode == 0:
            output = (result.stdout or "").strip()
            if output:
                phases = output.split()
                if phases and all(p in ["Running", "Succeeded"] for p in phases):
                    typer.secho(f"  Pods em {namespace} Ready.", fg=typer.colors.GREEN)
                    return True

        time.sleep(10)

    typer.secho(f"  Timeout aguardando pods em {namespace}.", fg=typer.colors.YELLOW)
    return False


def _install_argocd(ctx: ExecutionContext, node_name: str, admin_password: str) -> None:
    """Instala Argo CD via Helm."""
    typer.echo("\n=== Instalando Argo CD ===")

    # Add Helm repo
    run_cmd(["helm", "repo", "add", "argo", "https://argoproj.github.io/argo-helm"], ctx)
    run_cmd(["helm", "repo", "update"], ctx)

    # Create namespace
    run_cmd(
        ["kubectl", "create", "namespace", ARGOCD_NS],
        ctx,
        check=False,
    )

    # Values file with tolerations and nodeSelector
    values_yaml = f"""global:
  nodeSelector:
    kubernetes.io/hostname: {node_name}
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule

controller:
  replicas: 1

server:
  replicas: 1
  service:
    type: NodePort
    nodePortHttp: 30880
    nodePortHttps: 30443
  extraArgs:
    - --insecure  # Disable TLS for internal access (use Traefik for TLS termination)
  ingress:
    enabled: false  # We'll use Traefik IngressRoute

repoServer:
  replicas: 1

applicationSet:
  replicas: 1

redis:
  enabled: true

dex:
  enabled: false  # Disable Dex, use built-in auth

configs:
  params:
    server.insecure: true
  cm:
    url: https://argocd.local
    # Vault Plugin configuration (optional)
    configManagementPlugins: |
      - name: argocd-vault-plugin
        generate:
          command: ["argocd-vault-plugin"]
          args: ["generate", "./"]
  secret:
    # bcrypt hash of password (default: ArgoCD123!)
    argocdServerAdminPassword: "$2a$10$rRyBsGSHK6.uc8fntPwVIuLVHgsAhAX7TcdrqW/RADU0uh7CaChLa"
    argocdServerAdminPasswordMtime: "2024-01-01T00:00:00Z"
"""

    # If custom password provided, generate bcrypt hash
    if admin_password and admin_password != "ArgoCD123!":
        import subprocess
        # Use htpasswd or python to generate bcrypt
        try:
            result = subprocess.run(
                ["python3", "-c", f"import bcrypt; print(bcrypt.hashpw('{admin_password}'.encode(), bcrypt.gensalt()).decode())"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                hashed = result.stdout.strip()
                values_yaml = values_yaml.replace(
                    "$2a$10$rRyBsGSHK6.uc8fntPwVIuLVHgsAhAX7TcdrqW/RADU0uh7CaChLa",
                    hashed
                )
        except Exception:
            pass  # Use default password

    values_path = Path("/tmp/raijin-argocd-values.yaml")
    write_file(values_path, values_yaml, ctx)

    # Install Argo CD
    cmd = [
        "helm", "upgrade", "--install", "argocd",
        "argo/argo-cd",
        "-n", ARGOCD_NS,
        "-f", str(values_path),
        "--wait",
        "--timeout", "10m",
    ]

    run_cmd(cmd, ctx)

    if not ctx.dry_run:
        _wait_for_pods_ready(ctx, ARGOCD_NS, "app.kubernetes.io/part-of=argocd")


def _install_argo_workflows(ctx: ExecutionContext, node_name: str) -> None:
    """Instala Argo Workflows via Helm."""
    typer.echo("\n=== Instalando Argo Workflows ===")

    # Create namespace
    run_cmd(
        ["kubectl", "create", "namespace", ARGO_WORKFLOWS_NS],
        ctx,
        check=False,
    )

    # Values file
    values_yaml = f"""controller:
  nodeSelector:
    kubernetes.io/hostname: {node_name}
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  workflowDefaults:
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
        - key: node-role.kubernetes.io/master
          operator: Exists
          effect: NoSchedule
  containerRuntimeExecutor: emissary
  parallelism: 20
  
server:
  nodeSelector:
    kubernetes.io/hostname: {node_name}
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  service:
    type: NodePort
    nodePortHttp: 30881
  extraArgs:
    - --auth-mode=server  # Simple auth for internal use
  ingress:
    enabled: false

# Artifact Repository (MinIO integration)
artifactRepository:
  archiveLogs: true
  s3:
    endpoint: minio.minio.svc.cluster.local:9000
    bucket: argo-artifacts
    insecure: true
    accessKeySecret:
      name: argo-minio-credentials
      key: accesskey
    secretKeySecret:
      name: argo-minio-credentials
      key: secretkey

# Workflow RBAC
workflow:
  serviceAccount:
    create: true
    name: argo-workflow
"""

    values_path = Path("/tmp/raijin-argo-workflows-values.yaml")
    write_file(values_path, values_yaml, ctx)

    # Install Argo Workflows
    cmd = [
        "helm", "upgrade", "--install", "argo-workflows",
        "argo/argo-workflows",
        "-n", ARGO_WORKFLOWS_NS,
        "-f", str(values_path),
        "--wait",
        "--timeout", "10m",
    ]

    run_cmd(cmd, ctx)

    if not ctx.dry_run:
        _wait_for_pods_ready(ctx, ARGO_WORKFLOWS_NS, "app.kubernetes.io/part-of=argo-workflows")


def _create_traefik_ingress(ctx: ExecutionContext) -> None:
    """Cria IngressRoutes do Traefik para Argo CD e Workflows."""
    typer.echo("\n=== Criando IngressRoutes do Traefik ===")

    ingress_yaml = """---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: argocd
  namespace: argocd
spec:
  entryPoints:
    - websecure
  routes:
    - kind: Rule
      match: Host(`argocd.local`) || Host(`argocd.internal`)
      services:
        - name: argocd-server
          port: 80
  tls:
    secretName: argocd-tls
---
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: argo-workflows
  namespace: argo
spec:
  entryPoints:
    - websecure
  routes:
    - kind: Rule
      match: Host(`argo.local`) || Host(`argo.internal`)
      services:
        - name: argo-workflows-server
          port: 2746
  tls:
    secretName: argo-workflows-tls
"""

    ingress_path = Path("/tmp/raijin-argo-ingress.yaml")
    write_file(ingress_path, ingress_yaml, ctx)

    run_cmd(["kubectl", "apply", "-f", str(ingress_path)], ctx, check=False)


def _create_vault_integration(ctx: ExecutionContext) -> None:
    """Cria ExternalSecret para integração com Vault (opcional)."""
    typer.echo("\n=== Configurando integração com Vault ===")

    # Check if ClusterSecretStore vault-backend exists
    result = run_cmd(
        ["kubectl", "get", "clustersecretstore", "vault-backend"],
        ctx,
        check=False,
    )

    if result.returncode != 0:
        typer.echo("ClusterSecretStore 'vault-backend' não encontrado. Pulando integração com Vault.")
        typer.echo("Para integrar com Vault, primeiro instale o módulo 'secrets'.")
        return

    # Create ExternalSecret for Argo to access Vault secrets
    external_secret_yaml = """---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: argo-vault-secrets
  namespace: argocd
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: argo-vault-secrets
    creationPolicy: Owner
  data:
    - secretKey: git-token
      remoteRef:
        key: secret/data/cicd/git
        property: token
    - secretKey: docker-username
      remoteRef:
        key: secret/data/cicd/docker
        property: username
    - secretKey: docker-password
      remoteRef:
        key: secret/data/cicd/docker
        property: password
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: argo-vault-secrets
  namespace: argo
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: argo-vault-secrets
    creationPolicy: Owner
  data:
    - secretKey: git-token
      remoteRef:
        key: secret/data/cicd/git
        property: token
    - secretKey: docker-username
      remoteRef:
        key: secret/data/cicd/docker
        property: username
    - secretKey: docker-password
      remoteRef:
        key: secret/data/cicd/docker
        property: password
"""

    es_path = Path("/tmp/raijin-argo-externalsecret.yaml")
    write_file(es_path, external_secret_yaml, ctx)

    run_cmd(["kubectl", "apply", "-f", str(es_path)], ctx, check=False)

    typer.echo("\nPara usar secrets do Vault no Argo CD, crie os secrets no Vault:")
    typer.echo("  vault kv put secret/cicd/git token=<github-token>")
    typer.echo("  vault kv put secret/cicd/docker username=<user> password=<pass>")


def _show_access_info(admin_password: str) -> None:
    """Mostra informações de acesso."""
    typer.secho("\n" + "=" * 60, fg=typer.colors.GREEN)
    typer.secho("ARGO CD + ARGO WORKFLOWS INSTALADOS COM SUCESSO!", fg=typer.colors.GREEN, bold=True)
    typer.secho("=" * 60, fg=typer.colors.GREEN)

    typer.echo("\n📦 Argo CD (GitOps Continuous Delivery):")
    typer.echo("   URL: https://argocd.local ou http://<node-ip>:30443")
    typer.echo(f"   User: admin")
    typer.echo(f"   Password: {admin_password}")

    typer.echo("\n📦 Argo Workflows (CI Pipelines):")
    typer.echo("   URL: https://argo.local ou http://<node-ip>:30881")

    typer.echo("\n🔧 Comandos úteis:")
    typer.echo("   # Argo CD CLI")
    typer.echo("   argocd login argocd.local --username admin --password <pass> --insecure")
    typer.echo("   argocd app list")
    typer.echo("")
    typer.echo("   # Argo Workflows CLI")
    typer.echo("   argo list -n argo")
    typer.echo("   argo submit -n argo --watch examples/hello-world.yaml")

    typer.echo("\n📝 Para criar uma Application no Argo CD:")
    typer.echo("   argocd app create my-app \\")
    typer.echo("     --repo https://github.com/org/repo \\")
    typer.echo("     --path kubernetes/ \\")
    typer.echo("     --dest-server https://kubernetes.default.svc \\")
    typer.echo("     --dest-namespace default")

    typer.echo("\n🔐 Integração com Vault:")
    typer.echo("   O Argo já está configurado para usar secrets via External Secrets Operator.")
    typer.echo("   Crie secrets no Vault e use em suas Applications/Workflows.")


def run(ctx: ExecutionContext) -> None:
    """Instala Argo CD + Argo Workflows."""
    require_root(ctx)
    ensure_tool("helm", ctx, install_hint="Instale helm para implantar Argo.")

    typer.secho("\n" + "=" * 60, fg=typer.colors.CYAN)
    typer.secho("INSTALAÇÃO ARGO CD + ARGO WORKFLOWS", fg=typer.colors.CYAN, bold=True)
    typer.secho("GitOps CI/CD 100% Opensource - CNCF Graduated", fg=typer.colors.CYAN)
    typer.secho("=" * 60, fg=typer.colors.CYAN)

    # Prompts
    install_argocd = typer.confirm("Instalar Argo CD (GitOps)?", default=True)
    install_workflows = typer.confirm("Instalar Argo Workflows (CI)?", default=True)

    if not install_argocd and not install_workflows:
        typer.echo("Nenhum componente selecionado. Abortando.")
        raise typer.Abort()

    admin_password = "ArgoCD123!"
    if install_argocd:
        admin_password = typer.prompt(
            "Senha do admin do Argo CD",
            default="ArgoCD123!",
            hide_input=True,
            confirmation_prompt=True,
        )

    # Check existing installations
    if install_argocd and _check_existing_argocd(ctx):
        cleanup = typer.confirm(
            "Instalação anterior do Argo CD detectada. Reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_argocd(ctx)
        else:
            install_argocd = False

    if install_workflows and _check_existing_workflows(ctx):
        cleanup = typer.confirm(
            "Instalação anterior do Argo Workflows detectada. Reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_workflows(ctx)
        else:
            install_workflows = False

    node_name = _detect_node_name(ctx)

    # Install components
    if install_argocd:
        _install_argocd(ctx, node_name, admin_password)

    if install_workflows:
        _install_argo_workflows(ctx, node_name)

    # Create Traefik ingress
    if install_argocd or install_workflows:
        _create_traefik_ingress(ctx)

    # Setup Vault integration
    _create_vault_integration(ctx)

    # Show access info
    if not ctx.dry_run:
        _show_access_info(admin_password)


def uninstall(ctx: ExecutionContext) -> None:
    """Remove Argo CD e Argo Workflows."""
    require_root(ctx)

    typer.echo("Removendo Argo CD e Argo Workflows...")

    # Remove Argo CD
    if _check_existing_argocd(ctx):
        _uninstall_argocd(ctx)
        run_cmd(["kubectl", "delete", "namespace", ARGOCD_NS], ctx, check=False)

    # Remove Argo Workflows
    if _check_existing_workflows(ctx):
        _uninstall_workflows(ctx)
        run_cmd(["kubectl", "delete", "namespace", ARGO_WORKFLOWS_NS], ctx, check=False)

    typer.secho("✓ Argo CD e Argo Workflows removidos.", fg=typer.colors.GREEN)
