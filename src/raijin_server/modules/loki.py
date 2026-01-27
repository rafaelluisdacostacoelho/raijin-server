"""Configuracao do Loki via Helm."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Loki Stack via Helm...")

    values = [
        "promtail.enabled=true",
        "loki.persistence.enabled=true",
        "loki.persistence.size=20Gi",
        "loki.retentionPeriod=168h",  # 7 dias
    ]

    helm_upgrade_install(
        release="loki",
        chart="loki-stack",
        namespace="observability",
        repo="grafana",
        repo_url="https://grafana.github.io/helm-charts",
        ctx=ctx,
        values=values,
    )
