"""Automacao de sealed-secrets e external-secrets via Helm.

Instala os controladores necessários para criptografar e consumir segredos
em clusters Kubernetes. Inclui opcionalmente a exportacao do certificado
publico do sealed-secrets para permitir geracao de manifests lacrados.
"""

from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    ensure_tool,
    helm_upgrade_install,
    require_root,
    run_cmd,
)

SEALED_NAMESPACE = "kube-system"
ESO_NAMESPACE = "external-secrets"


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

    # sealed-secrets
    typer.secho("\n== Sealed Secrets ==", fg=typer.colors.CYAN, bold=True)
    helm_upgrade_install(
        "sealed-secrets",
        "sealed-secrets",
        sealed_ns,
        ctx,
        repo="bitnami-labs",
        repo_url="https://bitnami-labs.github.io/sealed-secrets",
        create_namespace=True,
    )

    typer.echo(
        "Para criar sealed-secrets a partir do seu desktop, exporte o certificado publico e use kubeseal."
    )
    if typer.confirm("Exportar certificado publico agora?", default=True):
        _export_sealed_cert(sealed_ns, ctx)

    # external-secrets
    typer.secho("\n== External Secrets Operator ==", fg=typer.colors.CYAN, bold=True)
    extra_args = ["--set", "installCRDs=true"]
    helm_upgrade_install(
        "external-secrets",
        "external-secrets",
        eso_ns,
        ctx,
        repo="external-secrets",
        repo_url="https://charts.external-secrets.io",
        create_namespace=True,
        extra_args=extra_args,
    )

    typer.echo(
        "External Secrets Operator instalado. Configure um SecretStore/ClusterSecretStore conforme seu provedor (AWS/GCP/Vault)."
    )

    typer.secho("\nDicas rapidas:", fg=typer.colors.GREEN)
    typer.echo("- Gere sealed-secrets localmente: kubeseal --controller-namespace <ns> --controller-name sealed-secrets < secret.yaml > sealed.yaml")
    typer.echo("- Para ESO: crie um SecretStore apontando para seu backend e um ExternalSecret referenciando os keys.")

