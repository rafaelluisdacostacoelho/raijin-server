"""Configuracao do Grafana via Helm com datasource e dashboards provisionados."""

import json
import socket
import tempfile
import textwrap
import time
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    helm_upgrade_install,
    kubectl_create_ns,
    require_root,
    run_cmd,
    write_file,
)

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


def _get_default_storage_class(ctx: ExecutionContext) -> str:
    """Retorna o nome da StorageClass default do cluster, se existir."""
    if ctx.dry_run:
        return ""
    result = run_cmd(
        [
            "kubectl",
            "get",
            "storageclass",
            "-o",
            "jsonpath={.items[?(@.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class=='true')].metadata.name}",
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
    
    # Patch no ConfigMap para os helper pods
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
    
    config_json_str = json.dumps(helper_pod_config)
    patch_data = json.dumps({"data": {"config.json": config_json_str}})
    
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
    
    # Reinicia o deployment
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
            "Abortando: Grafana com PVC requer uma StorageClass.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    if not _install_local_path_provisioner(ctx):
        raise typer.Exit(1)

    _set_default_storage_class(ctx, "local-path")
    return "local-path"


def _check_existing_grafana(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Grafana."""
    result = run_cmd(
        ["helm", "status", "grafana", "-n", "observability"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_grafana(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Grafana."""
    typer.echo("Removendo instalacao anterior do Grafana...")
    
    run_cmd(
        ["helm", "uninstall", "grafana", "-n", "observability"],
        ctx,
        check=False,
    )
    
    remove_data = typer.confirm("Remover PVCs (dados persistentes)?", default=False)
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "observability", "delete", "pvc", "-l", "app.kubernetes.io/name=grafana"],
            ctx,
            check=False,
        )
    
    time.sleep(5)


def _wait_for_grafana_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Grafana ficarem Ready."""
    typer.echo("Aguardando pods do Grafana ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "observability", "get", "pods",
                "-l", "app.kubernetes.io/name=grafana",
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
                    typer.secho("  Grafana Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Grafana.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Grafana via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_grafana(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Grafana detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_grafana(ctx)

    # Verifica se existe StorageClass default para sugerir no prompt
    default_sc = _get_default_storage_class(ctx)
    
    enable_persistence = typer.confirm(
        "Habilitar PVC para persistencia do Grafana?",
        default=bool(default_sc)
    )

    # Se habilitou PVC, garante que existe StorageClass disponivel
    if enable_persistence:
        default_sc = _ensure_storage_class(ctx)

    admin_password = typer.prompt("Senha admin do Grafana", default="admin")
    
    # NodePort para acesso via VPN (recomendado)
    enable_nodeport = typer.confirm(
        "Habilitar NodePort para acesso via VPN?",
        default=True
    )
    nodeport_port = 30030
    if enable_nodeport:
        nodeport_port = int(typer.prompt("Porta NodePort", default="30030"))
    
    # Ingress público não é recomendado para ferramentas de observabilidade
    enable_ingress = typer.confirm(
        "Habilitar ingress público? (NÃO recomendado - use VPN + NodePort)",
        default=False
    )
    
    ingress_host = "grafana.local"
    ingress_class = "traefik"
    tls_secret = "grafana-tls"
    
    if enable_ingress:
        typer.secho(
            "\n⚠️  ATENÇÃO: Expor Grafana publicamente é um risco de segurança!",
            fg=typer.colors.YELLOW,
            bold=True,
        )
        typer.secho(
            "Recomendação: Use VPN (raijin vpn) + port-forward para acesso seguro.\n",
            fg=typer.colors.YELLOW,
        )
        ingress_host = typer.prompt("Host para ingress", default="grafana.local")
        ingress_class = typer.prompt("IngressClass", default="traefik")
        tls_secret = typer.prompt("Secret TLS (cert-manager)", default="grafana-tls")
    
    persistence_size = "10Gi"
    storage_class = ""
    if enable_persistence:
        storage_class = typer.prompt(
            "StorageClass para PVC",
            default=default_sc or "",
        ).strip()
        persistence_size = typer.prompt("Tamanho do storage", default="10Gi")

    node_name = _detect_node_name(ctx)

    # Constroi o YAML de persistencia condicionalmente
    persistence_yaml = f"""persistence:
  enabled: {str(enable_persistence).lower()}"""
    
    if enable_persistence:
        persistence_yaml += f"""
  size: {persistence_size}"""
        if storage_class:
            persistence_yaml += f"""
  storageClassName: {storage_class}"""
    
    service_type = "NodePort" if enable_nodeport else "ClusterIP"
    values_yaml = f"""adminPassword: {admin_password}
service:
  type: {service_type}"""
    
    if enable_nodeport:
        values_yaml += f"""
  nodePort: {nodeport_port}"""
    
    values_yaml += f"""
ingress:
  enabled: {str(enable_ingress).lower()}"""
    
    if enable_ingress:
        values_yaml += f"""
  ingressClassName: {ingress_class}
  hosts:
    - {ingress_host}
  tls:
    - secretName: {tls_secret}
      hosts:
        - {ingress_host}"""
    
    values_yaml += f"""
{persistence_yaml}
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
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://kube-prometheus-stack-prometheus.observability.svc:9090
        isDefault: true
        jsonData:
          timeInterval: 30s
      - name: Loki
        type: loki
        access: proxy
        url: http://loki.observability.svc:3100
dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards/default
dashboards:
  default:
    kubernetes:
      gnetId: 6417
      revision: 1
      datasource: Prometheus
    node-exporter:
      gnetId: 1860
      revision: 27
      datasource: Prometheus
"""

    values_path = Path("/tmp/raijin-grafana-values.yaml")
    write_file(values_path, values_yaml, ctx)

    kubectl_create_ns("observability", ctx)

    if not enable_persistence:
        typer.secho(
            "PVC desativado: Grafana usara volume efemero (dados perdidos apos restart).",
            fg=typer.colors.YELLOW,
        )

    helm_upgrade_install(
        release="grafana",
        chart="grafana",
        namespace="observability",
        repo="grafana",
        repo_url="https://grafana.github.io/helm-charts",
        ctx=ctx,
        values=[],
        extra_args=["-f", str(values_path), "--wait", "--timeout", "10m", "--atomic"],
    )

    if not ctx.dry_run:
        _wait_for_grafana_ready(ctx)

    typer.secho("\n✓ Grafana instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    
    if enable_ingress:
        typer.echo(f"\nAcesse: https://{ingress_host}")
    elif enable_nodeport:
        typer.secho("\n🔒 Acesso via VPN + NodePort:", fg=typer.colors.CYAN, bold=True)
        typer.echo("\n1. Configure VPN (se ainda não tiver):")
        typer.echo("   sudo raijin vpn")
        typer.echo("\n2. Conecte via WireGuard no seu Windows/Mac")
        typer.echo("\n3. Acesse no navegador (IP da VPN):")
        typer.echo(f"   http://<VPN_SERVER_IP>:{nodeport_port}")
        typer.echo("\n   Exemplo: http://10.8.0.1:{}".format(nodeport_port))
    else:
        typer.secho("\n🔒 Acesso via Port-Forward:", fg=typer.colors.CYAN, bold=True)
        typer.echo("\n  kubectl -n observability port-forward svc/grafana 3000:80")
        typer.echo("\n  Acesse: http://localhost:3000")
    
    typer.echo("\nUsuario: admin")
    typer.echo(f"Senha: {admin_password}")
