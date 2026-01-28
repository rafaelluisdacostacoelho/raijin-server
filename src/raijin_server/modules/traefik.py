"""Configuracao do Traefik via Helm com TLS/ACME e ingressClass."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Traefik via Helm...")

    acme_email = typer.prompt("Email para ACME/Let's Encrypt", default="admin@example.com")
    dashboard_host = typer.prompt("Host para dashboard (opcional)", default="traefik.local")

    values = [
        "ingressClass.enabled=true",
        "ingressClass.isDefaultClass=true",
        "ports.web.redirectTo=websecure=true",
        "ports.websecure.tls.enabled=true",
        "service.type=LoadBalancer",
        f"certificatesResolvers.letsencrypt.acme.email={acme_email}",
        "certificatesResolvers.letsencrypt.acme.storage=/data/acme.json",
        "certificatesResolvers.letsencrypt.acme.httpChallenge.entryPoint=web",
        "logs.general.level=INFO",
        "providers.kubernetesIngress.ingressClass=traefik",
    ]

    if dashboard_host:
        values.append("ingressRoute.dashboard.enabled=true")
        values.append(f"ingressRoute.dashboard.match=Host(`{dashboard_host}`)")

    helm_upgrade_install(
        release="traefik",
        chart="traefik",
        namespace="traefik",
        repo="traefik",
        repo_url="https://traefik.github.io/charts",
        ctx=ctx,
        values=values,
    )
