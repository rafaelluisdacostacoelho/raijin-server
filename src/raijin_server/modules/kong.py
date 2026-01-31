"""Configuracao do Kong Gateway via Helm com configuracoes production-ready."""

import socket
import time
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root, run_cmd, write_file


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


def _check_metallb_installed(ctx: ExecutionContext) -> bool:
    """Verifica se MetalLB está instalado no cluster."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "metallb-controller", "-n", "metallb-system"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_cert_manager_installed(ctx: ExecutionContext) -> bool:
    """Verifica se cert-manager está instalado no cluster."""
    result = run_cmd(
        ["kubectl", "get", "deployment", "cert-manager", "-n", "cert-manager"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_existing_kong(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Kong."""
    result = run_cmd(
        ["helm", "status", "kong", "-n", "kong"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _check_orphan_crds(ctx: ExecutionContext) -> list[str]:
    """Detecta CRDs do Kong que existem sem ownership do Helm."""
    result = run_cmd(
        ["kubectl", "get", "crd", "-o", "name"],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        return []
    
    kong_crds = []
    for line in (result.stdout or "").strip().split("\n"):
        if "konghq.com" in line:
            # Extrai nome do CRD
            crd_name = line.replace("customresourcedefinition.apiextensions.k8s.io/", "")
            kong_crds.append(crd_name)
    
    return kong_crds


def _adopt_crds_for_helm(ctx: ExecutionContext, crds: list[str]) -> bool:
    """Adiciona labels do Helm aos CRDs existentes para permitir adocao."""
    typer.echo(f"Adicionando labels Helm a {len(crds)} CRDs existentes...")
    
    for crd in crds:
        # Adiciona label managed-by
        run_cmd(
            ["kubectl", "label", "crd", crd, "app.kubernetes.io/managed-by=Helm", "--overwrite"],
            ctx,
            check=False,
        )
        # Adiciona annotations de release
        run_cmd(
            ["kubectl", "annotate", "crd", crd, "meta.helm.sh/release-name=kong", "--overwrite"],
            ctx,
            check=False,
        )
        run_cmd(
            ["kubectl", "annotate", "crd", crd, "meta.helm.sh/release-namespace=kong", "--overwrite"],
            ctx,
            check=False,
        )
    
    typer.secho("  ✓ CRDs preparados para adocao pelo Helm.", fg=typer.colors.GREEN)
    return True


def _cleanup_orphan_crds(ctx: ExecutionContext, crds: list[str]) -> bool:
    """Remove CRDs do Kong completamente."""
    typer.echo(f"Removendo {len(crds)} CRDs do Kong...")
    
    for crd in crds:
        run_cmd(
            ["kubectl", "delete", "crd", crd, "--ignore-not-found", "--wait=true"],
            ctx,
            check=False,
        )
    
    # Aguarda e verifica se foram realmente removidos
    typer.echo("  Aguardando remocao completa dos CRDs...")
    max_attempts = 10
    for attempt in range(max_attempts):
        time.sleep(2)
        remaining = _check_orphan_crds(ctx)
        if not remaining:
            typer.secho("  ✓ CRDs removidos com sucesso.", fg=typer.colors.GREEN)
            return True
        
        if attempt < max_attempts - 1:
            typer.echo(f"  Ainda restam {len(remaining)} CRDs. Tentando remover novamente...")
            for crd in remaining:
                run_cmd(
                    ["kubectl", "delete", "crd", crd, "--ignore-not-found", "--wait=true", "--timeout=30s"],
                    ctx,
                    check=False,
                )
    
    remaining = _check_orphan_crds(ctx)
    if remaining:
        typer.secho(f"  ⚠️  {len(remaining)} CRDs ainda existem:", fg=typer.colors.YELLOW)
        for crd in remaining[:5]:
            typer.echo(f"      - {crd}")
        return False
    
    return True


def _uninstall_kong(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Kong completamente, incluindo CRDs."""
    typer.echo("Removendo instalacao anterior do Kong...")
    
    run_cmd(
        ["helm", "uninstall", "kong", "-n", "kong"],
        ctx,
        check=False,
    )
    
    run_cmd(
        ["kubectl", "delete", "namespace", "kong", "--ignore-not-found", "--wait=false"],
        ctx,
        check=False,
    )
    
    # Remove CRDs do Kong diretamente (mais confiável)
    typer.echo("Removendo CRDs do Kong...")
    run_cmd(
        ["sh", "-c", "kubectl get crd -o name | grep konghq.com | xargs -r kubectl delete --ignore-not-found"],
        ctx,
        check=False,
    )
    
    # Aguarda namespace terminar de deletar
    typer.echo("Aguardando limpeza completa...")
    run_cmd(
        ["kubectl", "wait", "--for=delete", "namespace/kong", "--timeout=60s"],
        ctx,
        check=False,
    )
    
    time.sleep(3)


def _wait_for_kong_ready(ctx: ExecutionContext, timeout: int = 180) -> bool:
    """Aguarda pods do Kong ficarem Ready."""
    typer.echo("Aguardando pods do Kong ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "kong", "get", "pods",
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
    
    typer.secho("  Timeout aguardando pods do Kong.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Kong Gateway via Helm...")

    # Prompt opcional de limpeza
    if _check_existing_kong(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Kong detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_kong(ctx)
    
    # Verificar CRDs existentes do Kong (sem ownership do Helm)
    existing_crds = _check_orphan_crds(ctx)
    skip_crds = False
    
    if existing_crds:
        typer.secho(
            f"\n⚠️  Detectados {len(existing_crds)} CRDs do Kong sem labels do Helm:",
            fg=typer.colors.YELLOW,
        )
        for crd in existing_crds[:5]:
            typer.echo(f"    - {crd}")
        if len(existing_crds) > 5:
            typer.echo(f"    ... e mais {len(existing_crds) - 5}")
        
        typer.echo("\nOpcoes:")
        typer.echo("  1. Adotar CRDs existentes (adicionar labels Helm) - RECOMENDADO")
        typer.echo("  2. Deletar CRDs e deixar Helm recriar")
        typer.echo("  3. Ignorar CRDs (usar --skip-crds)")
        typer.echo("  4. Cancelar instalacao")
        
        choice = typer.prompt("Escolha", default="1")
        
        if choice == "1":
            _adopt_crds_for_helm(ctx, existing_crds)
        elif choice == "2":
            cleanup_success = _cleanup_orphan_crds(ctx, existing_crds)
            if not cleanup_success:
                if not typer.confirm("CRDs ainda existem. Continuar mesmo assim?", default=False):
                    typer.secho("Instalacao cancelada.", fg=typer.colors.RED)
                    return
        elif choice == "3":
            skip_crds = True
            typer.secho("Helm não gerenciará os CRDs existentes.", fg=typer.colors.YELLOW)
        else:
            typer.secho("Instalacao cancelada.", fg=typer.colors.RED)
            return

    # Detectar dependencias
    has_metallb = _check_metallb_installed(ctx)
    has_cert_manager = _check_cert_manager_installed(ctx)

    # Tipo de servico baseado na presenca do MetalLB
    if has_metallb:
        typer.secho("✓ MetalLB detectado. Kong usará LoadBalancer.", fg=typer.colors.GREEN)
        service_type = "LoadBalancer"
    else:
        typer.secho("⚠ MetalLB não detectado. Kong usará NodePort.", fg=typer.colors.YELLOW)
        service_type = "NodePort"

    if has_cert_manager:
        typer.secho("✓ cert-manager detectado. TLS automático disponível.", fg=typer.colors.GREEN)
    else:
        typer.secho("⚠ cert-manager não detectado. Configure TLS manualmente.", fg=typer.colors.YELLOW)

    # Configuracoes interativas
    enable_admin = typer.confirm("Habilitar Admin API (para gerenciamento)?", default=True)
    enable_metrics = typer.confirm("Habilitar métricas Prometheus?", default=True)
    db_mode = typer.prompt(
        "Modo de banco de dados (off/postgres)",
        default="off",
    )
    
    # Normaliza valores antigos
    if db_mode == "dbless":
        db_mode = "off"
    
    node_name = _detect_node_name(ctx)

    # Configurações base do values.yaml
    values_yaml = f"""env:
  database: "{db_mode}"

ingressController:
  installCRDs: true
  enabled: true

proxy:
  enabled: true
  type: {service_type}
  http:
    enabled: true
    containerPort: 8000
    servicePort: 80
  tls:
    enabled: true
    containerPort: 8443
    servicePort: 443

admin:
  enabled: {str(enable_admin).lower()}
  type: ClusterIP
  http:
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
    memory: 256Mi
    cpu: 100m
  limits:
    memory: 1Gi
"""

    # Configurações específicas para modo off/dbless (desabilita PostgreSQL e migrations)
    if db_mode == "off":
        values_yaml += """
# Modo dbless (off) - sem banco de dados
postgresql:
  enabled: false

migrations:
  preUpgrade: false
  postUpgrade: false
"""

    # Adicionar métricas se habilitado
    if enable_metrics:
        values_yaml += """
serviceMonitor:
  enabled: true
  namespace: kong
  labels:
    release: kube-prometheus-stack

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8100"
"""

    values_path = Path("/tmp/raijin-kong-values.yaml")
    write_file(values_path, values_yaml, ctx)

    run_cmd(["kubectl", "create", "namespace", "kong"], ctx, check=False)
    
    # Monta args extras para o helm
    extra_args = ["-f", str(values_path)]
    if skip_crds:
        extra_args.append("--skip-crds")
    
    helm_upgrade_install(
        release="kong",
        chart="kong",
        namespace="kong",
        repo="kong",
        repo_url="https://charts.konghq.com",
        ctx=ctx,
        values=[],
        extra_args=extra_args,
    )
    
    # Aguarda pods ficarem prontos
    if not ctx.dry_run:
        _wait_for_kong_ready(ctx)
    
    # Mostra informacoes uteis
    typer.secho("\n✓ Kong Gateway instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    
    typer.echo("\n📌 Acesso ao Kong Proxy:")
    if service_type == "LoadBalancer":
        typer.echo("  kubectl -n kong get svc kong-kong-proxy  # Aguarde EXTERNAL-IP")
    else:
        typer.echo("  kubectl -n kong get svc kong-kong-proxy  # Use NodePort")
    
    if enable_admin:
        typer.echo("\n📌 Admin API (port-forward):")
        typer.echo("  kubectl -n kong port-forward svc/kong-kong-admin 8001:8001")
        typer.echo("  curl http://localhost:8001/status")
    
    if enable_metrics:
        typer.echo("\n📌 Métricas Prometheus:")
        typer.echo("  ServiceMonitor criado - métricas serão coletadas automaticamente")
    
    if has_cert_manager:
        typer.echo("\n📌 TLS com cert-manager (exemplo de Ingress):")
        typer.echo("""  ---
  apiVersion: networking.k8s.io/v1
  kind: Ingress
  metadata:
    name: my-api
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
      konghq.com/strip-path: "true"
  spec:
    ingressClassName: kong
    tls:
      - hosts: [api.example.com]
        secretName: api-tls
    rules:
      - host: api.example.com
        http:
          paths:
            - path: /
              pathType: Prefix
              backend:
                service:
                  name: my-service
                  port:
                    number: 80""")
