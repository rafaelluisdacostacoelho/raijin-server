"""Instala e configura cert-manager com emissores ACME (HTTP-01 ou DNS-01)."""

from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    ensure_tool,
    helm_upgrade_install,
    kubectl_apply,
    require_root,
    write_file,
)

CHART_REPO = "https://charts.jetstack.io"
CHART_NAME = "cert-manager"
NAMESPACE = "cert-manager"
MANIFEST_PATH = Path("/tmp/raijin-cert-manager-issuer.yaml")


def _build_http01_issuer(name: str, email: str, ingress_class: str, staging: bool) -> str:
    server = (
        "https://acme-staging-v02.api.letsencrypt.org/directory"
        if staging
        else "https://acme-v02.api.letsencrypt.org/directory"
    )
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {name}
spec:
  acme:
    email: {email}
    server: {server}
    privateKeySecretRef:
      name: {name}
    solvers:
      - http01:
          ingress:
            class: {ingress_class}
"""


def _build_cloudflare_dns01(name: str, email: str, secret_name: str, staging: bool) -> str:
    server = (
        "https://acme-staging-v02.api.letsencrypt.org/directory"
        if staging
        else "https://acme-v02.api.letsencrypt.org/directory"
    )
    return f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {name}
spec:
  acme:
    email: {email}
    server: {server}
    privateKeySecretRef:
      name: {name}
    solvers:
      - dns01:
          cloudflare:
            apiTokenSecretRef:
              name: {secret_name}
              key: api-token
"""


def _build_cloudflare_secret(secret_name: str, api_token: str) -> str:
    return f"""apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: {NAMESPACE}
type: Opaque
stringData:
  api-token: {api_token}
"""


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("helm", ctx, install_hint="Instale helm ou use --dry-run para simular.")
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou use --dry-run para simular.")

    typer.echo("Instalando cert-manager via Helm...")
    email = typer.prompt("Email para ACME (Let's Encrypt)", default="admin@example.com")
    solver = typer.prompt("Tipo de desafio (http01/dns01)", default="http01")

    helm_upgrade_install(
        release="cert-manager",
        chart=CHART_NAME,
        namespace=NAMESPACE,
        ctx=ctx,
        repo="jetstack",
        repo_url=CHART_REPO,
        create_namespace=True,
        extra_args=["--set", "installCRDs=true"],
    )

    issuer_docs = []

    if solver.lower() == "dns01":
        typer.secho("DNS-01 selecionado (Cloudflare)", fg=typer.colors.CYAN)
        issuer_name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-dns")
        staging = typer.confirm("Usar endpoint de staging? (para testes)", default=False)
        secret_name = typer.prompt("Secret com API token do Cloudflare", default="cloudflare-api-token")
        api_token = typer.prompt("Informe o API token do Cloudflare", hide_input=True)

        issuer_docs.append(_build_cloudflare_secret(secret_name, api_token))
        issuer_docs.append(_build_cloudflare_dns01(issuer_name, email, secret_name, staging))
    else:
        typer.secho("HTTP-01 selecionado (Ingress)", fg=typer.colors.CYAN)
        issuer_name = typer.prompt("Nome do ClusterIssuer", default="letsencrypt-http")
        staging = typer.confirm("Usar endpoint de staging? (para testes)", default=False)
        ingress_class = typer.prompt("IngressClass para resolver HTTP-01", default="traefik")

        issuer_docs.append(_build_http01_issuer(issuer_name, email, ingress_class, staging))

    manifest = "---\n".join(issuer_docs)
    write_file(MANIFEST_PATH, manifest, ctx)
    kubectl_apply(str(MANIFEST_PATH), ctx)

    typer.secho("cert-manager instalado e issuer aplicado.", fg=typer.colors.GREEN)
    typer.echo("Execute um Certificate/Ingress apontando para o ClusterIssuer para emitir certificados.")

