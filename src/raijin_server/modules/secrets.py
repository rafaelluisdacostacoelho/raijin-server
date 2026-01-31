"""Automacao de sealed-secrets e external-secrets via Helm (production-ready).

Instala os controladores necessários para criptografar e consumir segredos
em clusters Kubernetes. Inclui opcionalmente a exportacao do certificado
publico do sealed-secrets para permitir geracao de manifests lacrados.
"""

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

SEALED_NAMESPACE = "kube-system"
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


def _check_existing_sealed_secrets(ctx: ExecutionContext, namespace: str) -> bool:
    """Verifica se existe instalacao do Sealed Secrets."""
    result = run_cmd(
        ["helm", "status", "sealed-secrets", "-n", namespace],
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


def _uninstall_sealed_secrets(ctx: ExecutionContext, namespace: str) -> None:
    """Remove instalacao anterior do Sealed Secrets."""
    typer.echo("Removendo instalacao anterior do Sealed Secrets...")
    
    run_cmd(
        ["helm", "uninstall", "sealed-secrets", "-n", namespace],
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


def _wait_for_sealed_secrets_ready(ctx: ExecutionContext, namespace: str, timeout: int = 120) -> bool:
    """Aguarda pods do Sealed Secrets ficarem Ready."""
    typer.echo("Aguardando pods do Sealed Secrets ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", namespace, "get", "pods",
                "-l", "app.kubernetes.io/name=sealed-secrets",
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
                    typer.secho("  Sealed Secrets Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(5)
    
    typer.secho("  Timeout aguardando Sealed Secrets.", fg=typer.colors.YELLOW)
    return False


def _export_sealed_cert(namespace: str, ctx: ExecutionContext) -> None:
    """Exporta o certificado publico do sealed-secrets para um caminho local."""

    default_path = Path("/tmp/sealed-secrets-cert.pem")
    dest = typer.prompt(
        "Caminho para salvar o certificado publico do sealed-secrets",
        default=str(default_path),
    )
    typer.echo(f"Exportando certificado para {dest}...")
    cmd = [
        "kubectl",
        "-n",
        namespace,
        "get",
        "secret",
        "-l",
        "sealedsecrets.bitnami.com/sealed-secrets-key",
        "-o",
        r"jsonpath={.items[0].data.tls\.crt}",
    ]
    result = run_cmd(cmd, ctx, check=False)
    if result.returncode != 0:
        typer.secho("Nao foi possivel obter o certificado (tente novamente apos o pod estar Ready).", fg=typer.colors.YELLOW)
        return

    try:
        import base64

        cert_b64 = result.stdout.strip()
        cert_bytes = base64.b64decode(cert_b64)
        Path(dest).write_bytes(cert_bytes)
        typer.secho(f"✓ Certificado salvo em {dest}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(f"Falha ao decodificar/salvar certificado: {exc}", fg=typer.colors.YELLOW)


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    ensure_tool("helm", ctx, install_hint="Instale helm ou habilite dry-run.")

    typer.echo("Instalando sealed-secrets e external-secrets...")

    sealed_ns = typer.prompt("Namespace para sealed-secrets", default=SEALED_NAMESPACE)
    eso_ns = typer.prompt("Namespace para external-secrets", default=ESO_NAMESPACE)

    node_name = _detect_node_name(ctx)

    # sealed-secrets
    typer.secho("\n== Sealed Secrets ==", fg=typer.colors.CYAN, bold=True)

    # Prompt opcional de limpeza
    if _check_existing_sealed_secrets(ctx, sealed_ns):
        cleanup = typer.confirm(
            "Instalacao anterior do Sealed Secrets detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_sealed_secrets(ctx, sealed_ns)

    sealed_values_yaml = f"""tolerations:
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

    sealed_values_path = Path("/tmp/raijin-sealed-secrets-values.yaml")
    write_file(sealed_values_path, sealed_values_yaml, ctx)

    helm_upgrade_install(
        "sealed-secrets",
        "sealed-secrets",
        sealed_ns,
        ctx,
        repo="bitnami-labs",
        repo_url="https://bitnami-labs.github.io/sealed-secrets",
        create_namespace=True,
        extra_args=["-f", str(sealed_values_path)],
    )

    if not ctx.dry_run:
        _wait_for_sealed_secrets_ready(ctx, sealed_ns)

    typer.echo(
        "Para criar sealed-secrets a partir do seu desktop, exporte o certificado publico e use kubeseal."
    )
    if typer.confirm("Exportar certificado publico agora?", default=True):
        _export_sealed_cert(sealed_ns, ctx)

    # external-secrets
    typer.secho("\n== External Secrets Operator ==", fg=typer.colors.CYAN, bold=True)

    # Prompt opcional de limpeza
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

    typer.secho("\n✓ Secrets management instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo(
        "\nExternal Secrets Operator instalado. Configure um SecretStore/ClusterSecretStore conforme seu provedor (AWS/GCP/Vault)."
    )

    typer.secho("\nDicas rapidas:", fg=typer.colors.GREEN)
    typer.echo(f"- Gere sealed-secrets localmente: kubeseal --controller-namespace {sealed_ns} --controller-name sealed-secrets < secret.yaml > sealed.yaml")
    typer.echo("- Para ESO: crie um SecretStore apontando para seu backend e um ExternalSecret referenciando os keys.")

