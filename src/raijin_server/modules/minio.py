"""Deploy do MinIO via Helm com configuracoes production-ready."""

import json
import secrets
import socket
import tempfile
import time
from pathlib import Path
import textwrap

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, run_cmd

LOCAL_PATH_PROVISIONER_URL = (
    "https://raw.githubusercontent.com/rancher/local-path-provisioner/"
    "v0.0.30/deploy/local-path-storage.yaml"
)


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


def _generate_secret(length: int = 32) -> str:
    """Gera secret aleatório seguro."""
    return secrets.token_urlsafe(length)[:length]


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


def _get_default_storage_class(ctx: ExecutionContext) -> str:
    """Retorna o nome da StorageClass default do cluster, se existir."""
    result = run_cmd(
        [
            "kubectl", "get", "storageclass",
            "-o", "jsonpath={.items[?(@.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class=='true')].metadata.name}",
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        return (result.stdout or "").strip()
    return ""


def _list_storage_classes(ctx: ExecutionContext) -> list:
    """Lista todas as StorageClasses disponiveis."""
    result = run_cmd(
        ["kubectl", "get", "storageclass", "-o", "jsonpath={.items[*].metadata.name}"],
        ctx,
        check=False,
    )
    if result.returncode == 0 and (result.stdout or "").strip():
        return (result.stdout or "").strip().split()
    return []


def _patch_local_path_provisioner_tolerations(ctx: ExecutionContext) -> None:
    """Adiciona tolerations ao local-path-provisioner para rodar em control-plane."""
    typer.echo("  Configurando tolerations no local-path-provisioner...")
    
    # Patch no deployment para tolerar control-plane
    patch_deployment = textwrap.dedent(
        """
        spec:
          template:
            spec:
              tolerations:
              - key: node-role.kubernetes.io/control-plane
                operator: Exists
                effect: NoSchedule
              - key: node-role.kubernetes.io/master
                operator: Exists
                effect: NoSchedule
        """
    ).strip()
    
    result = run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "patch", "deployment",
            "local-path-provisioner", "--patch", patch_deployment,
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        typer.secho("    ✓ Deployment patched com tolerations.", fg=typer.colors.GREEN)
    
    # Patch no ConfigMap para os helper pods (que criam os dirs no node)
    # O local-path-provisioner usa um ConfigMap com helperPod template
    helper_pod_config = {
        "nodePathMap": [
            {
                "node": "DEFAULT_PATH_FOR_NON_LISTED_NODES",
                "paths": ["/opt/local-path-provisioner"]
            }
        ],
        "setupCommand": None,
        "teardownCommand": None,
        "helperPod": {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {},
            "spec": {
                "tolerations": [
                    {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
                    {"key": "node-role.kubernetes.io/master", "operator": "Exists", "effect": "NoSchedule"}
                ],
                "containers": [
                    {
                        "name": "helper-pod",
                        "image": "busybox:stable",
                        "imagePullPolicy": "IfNotPresent"
                    }
                ]
            }
        }
    }
    
    # Converte para JSON string para o patch
    config_json_str = json.dumps(helper_pod_config)
    patch_data = json.dumps({"data": {"config.json": config_json_str}})
    
    # Aplica via patch no ConfigMap
    result = run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "patch", "configmap",
            "local-path-config", "--type=merge", "-p", patch_data,
        ],
        ctx,
        check=False,
    )
    if result.returncode == 0:
        typer.secho("    ✓ ConfigMap patched para helper pods.", fg=typer.colors.GREEN)
    
    # Reinicia o deployment para aplicar as mudanças
    run_cmd(
        ["kubectl", "-n", "local-path-storage", "rollout", "restart", "deployment/local-path-provisioner"],
        ctx,
        check=False,
    )
    
    # Aguarda rollout
    run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "rollout", "status",
            "deployment/local-path-provisioner", "--timeout=60s",
        ],
        ctx,
        check=False,
    )


def _install_local_path_provisioner(ctx: ExecutionContext) -> bool:
    """Instala local-path-provisioner para usar storage local (NVMe/SSD)."""
    typer.echo("Instalando local-path-provisioner para storage local...")
    
    result = run_cmd(
        ["kubectl", "apply", "-f", LOCAL_PATH_PROVISIONER_URL],
        ctx,
        check=False,
    )
    if result.returncode != 0:
        typer.secho("  Falha ao instalar local-path-provisioner.", fg=typer.colors.RED)
        return False
    
    # Aguarda deployment ficar pronto inicialmente
    typer.echo("  Aguardando local-path-provisioner ficar Ready...")
    run_cmd(
        [
            "kubectl", "-n", "local-path-storage", "rollout", "status",
            "deployment/local-path-provisioner", "--timeout=60s",
        ],
        ctx,
        check=False,
    )
    
    # Aplica tolerations para control-plane (single-node clusters)
    _patch_local_path_provisioner_tolerations(ctx)
    
    typer.secho("  ✓ local-path-provisioner instalado e configurado.", fg=typer.colors.GREEN)
    return True


def _set_default_storage_class(ctx: ExecutionContext, name: str) -> None:
    """Define uma StorageClass como default."""
    # Remove default de outras classes primeiro
    existing = _list_storage_classes(ctx)
    for sc in existing:
        if sc != name:
            run_cmd(
                [
                    "kubectl", "annotate", "storageclass", sc,
                    "storageclass.kubernetes.io/is-default-class-",
                    "--overwrite",
                ],
                ctx,
                check=False,
            )
    
    # Define a nova como default
    run_cmd(
        [
            "kubectl", "annotate", "storageclass", name,
            "storageclass.kubernetes.io/is-default-class=true",
            "--overwrite",
        ],
        ctx,
        check=True,
    )
    typer.secho(f"  ✓ StorageClass '{name}' definida como default.", fg=typer.colors.GREEN)


def _ensure_storage_class(ctx: ExecutionContext) -> str:
    """Garante que existe uma StorageClass disponivel, instalando local-path se necessario."""
    if ctx.dry_run:
        return "local-path"  # Retorna um valor dummy para dry-run
    
    default_sc = _get_default_storage_class(ctx)
    available = _list_storage_classes(ctx)

    # Se ja existir default (qualquer uma), usa ela
    if default_sc:
        typer.echo(f"StorageClass default detectada: {default_sc}")
        # Se for local-path, garante que o provisioner tem tolerations
        if default_sc == "local-path" or "local-path" in available:
            _patch_local_path_provisioner_tolerations(ctx)
        return default_sc

    # Se local-path estiver disponivel mas nao for default, define como default
    if "local-path" in available:
        typer.echo("StorageClass 'local-path' detectada.")
        _patch_local_path_provisioner_tolerations(ctx)
        _set_default_storage_class(ctx, "local-path")
        return "local-path"

    # Se houver outras classes disponiveis, pergunta qual usar
    if available:
        typer.echo(f"StorageClasses disponiveis (sem default): {', '.join(available)}")
        choice = typer.prompt(
            f"Qual StorageClass usar? ({'/'.join(available)})",
            default=available[0],
        )
        return choice

    # Nenhuma StorageClass disponivel - instala local-path automaticamente
    typer.secho(
        "Nenhuma StorageClass encontrada no cluster.",
        fg=typer.colors.YELLOW,
    )
    install = typer.confirm(
        "Instalar local-path-provisioner para usar armazenamento local (NVMe/SSD)?",
        default=True,
    )
    if not install:
        typer.secho(
            "Abortando: MinIO requer uma StorageClass para PVCs.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    if not _install_local_path_provisioner(ctx):
        raise typer.Exit(1)

    _set_default_storage_class(ctx, "local-path")
    return "local-path"


def _check_existing_minio(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do MinIO."""
    result = run_cmd(
        ["helm", "status", "minio", "-n", "minio"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_minio(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do MinIO."""
    typer.echo("Removendo instalacao anterior do MinIO...")
    
    run_cmd(
        ["helm", "uninstall", "minio", "-n", "minio"],
        ctx,
        check=False,
    )
    
    # Pergunta se quer remover PVCs (dados)
    remove_data = typer.confirm(
        "Remover PVCs (dados persistentes)?",
        default=False,
    )
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "minio", "delete", "pvc", "--all"],
            ctx,
            check=False,
        )
    
    run_cmd(
        ["kubectl", "delete", "namespace", "minio", "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    time.sleep(5)


def _wait_for_minio_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do MinIO ficarem Ready."""
    typer.echo("Aguardando pods do MinIO ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "minio", "get", "pods",
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
                    typer.secho(f"  Todos os {len(pods)} pods Running.", fg=typer.colors.GREEN)
                    return True
                
                pending = [name for name, phase in pods if phase != "Running"]
                if pending:
                    typer.echo(f"  Aguardando: {', '.join(pending[:3])}...")
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando pods do MinIO.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando MinIO via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_minio(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do MinIO detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_minio(ctx)

    # Garante que existe StorageClass (instala local-path-provisioner se necessario)
    storage_class = _ensure_storage_class(ctx)

    # Configuracoes interativas
    mode = typer.prompt(
        "Modo de operacao (standalone/distributed)",
        default="standalone",
    )
    is_distributed = mode.lower().startswith("d")

    replicas = 1
    resources_req_cpu = "250m"
    resources_req_mem = "512Mi"
    resources_lim_cpu = "500m"
    resources_lim_mem = "1Gi"

    if is_distributed:
        replicas = typer.prompt(
            "Qtd de pods MinIO (replicas)",
            default="4",
        )
        resources_req_cpu = typer.prompt(
            "CPU request por pod (distributed)",
            default="500m",
        )
        resources_req_mem = typer.prompt(
            "Memoria request por pod (distributed)",
            default="1Gi",
        )
        resources_lim_cpu = typer.prompt(
            "CPU limit por pod (distributed)",
            default="1",
        )
        resources_lim_mem = typer.prompt(
            "Memoria limit por pod (distributed)",
            default="2Gi",
        )
    
    root_user = typer.prompt("Root user (admin)", default="minio-admin")
    root_password = typer.prompt(
        "Root password (deixe vazio para gerar)",
        default="",
        hide_input=True,
    )
    if not root_password:
        root_password = _generate_secret(24)
        typer.secho(f"  Password gerado: {root_password}", fg=typer.colors.CYAN)
    
    persistence_size = typer.prompt("Tamanho do storage (ex: 10Gi, 50Gi)", default="10Gi")
    
    # Permite override da StorageClass detectada
    storage_class_override = typer.prompt(
        f"StorageClass para os PVCs (detectada: {storage_class})",
        default=storage_class,
    ).strip()
    if storage_class_override:
        storage_class = storage_class_override
    
    enable_console = typer.confirm("Habilitar Console Web?", default=True)
    
    node_name = _detect_node_name(ctx)
    
    values = [
        f"mode={mode}",
        f"rootUser={root_user}",
        f"rootPassword={root_password}",
        # Persistence
        "persistence.enabled=true",
        f"persistence.size={persistence_size}",
        f"persistence.storageClass={storage_class}",
        # Resources
        f"resources.requests.memory={resources_req_mem}",
        f"resources.requests.cpu={resources_req_cpu}",
        f"resources.limits.memory={resources_lim_mem}",
        f"resources.limits.cpu={resources_lim_cpu}",
        # Tolerations para control-plane
        "tolerations[0].key=node-role.kubernetes.io/control-plane",
        "tolerations[0].operator=Exists",
        "tolerations[0].effect=NoSchedule",
        "tolerations[1].key=node-role.kubernetes.io/master",
        "tolerations[1].operator=Exists",
        "tolerations[1].effect=NoSchedule",
        # NodeSelector
        f"nodeSelector.kubernetes\\.io/hostname={node_name}",
        # Post-job (fixtures/config) para honrar tolerations/nodeSelector e nao travar em taint
        "postJob.tolerations[0].key=node-role.kubernetes.io/control-plane",
        "postJob.tolerations[0].operator=Exists",
        "postJob.tolerations[0].effect=NoSchedule",
        "postJob.tolerations[1].key=node-role.kubernetes.io/master",
        "postJob.tolerations[1].operator=Exists",
        "postJob.tolerations[1].effect=NoSchedule",
        f"postJob.nodeSelector.kubernetes\\.io/hostname={node_name}",
    ]

    if is_distributed:
        values.append(f"replicas={replicas}")
    
    # Console
    if enable_console:
        values.extend([
            "consoleService.type=ClusterIP",
            "consoleIngress.enabled=false",
        ])
    
    helm_upgrade_install(
        release="minio",
        chart="minio",
        namespace="minio",
        repo="minio",
        repo_url="https://charts.min.io/",
        ctx=ctx,
        values=values,
    )
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_minio_ready(ctx)
    
    # Mostra informacoes uteis
    typer.secho("\n✓ MinIO instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nCredenciais:")
    typer.echo(f"  Root User: {root_user}")
    typer.echo(f"  Root Password: {root_password}")
    
    if enable_console:
        typer.secho("\n🔒 Acesso Seguro ao MinIO Console via VPN:", fg=typer.colors.CYAN, bold=True)
        typer.echo("\n1. Configure VPN (se ainda não tiver):")
        typer.echo("   sudo raijin vpn")
        typer.echo("\n2. Conecte via WireGuard")
        typer.echo("\n3. Faça port-forward:")
        typer.echo("   kubectl -n minio port-forward svc/minio-console 9001:9001")
        typer.echo("\n4. Acesse no navegador:")
        typer.echo("   http://localhost:9001")
    
    typer.echo("\nPara acessar a API S3 (port-forward):")
    typer.echo("  kubectl -n minio port-forward svc/minio 9000:9000")
