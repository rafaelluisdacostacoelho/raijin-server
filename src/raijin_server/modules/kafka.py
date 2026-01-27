"""Deploy do Apache Kafka via Helm (Bitnami OCI)."""

import typer

from raijin_server.utils import ExecutionContext, helm_upgrade_install, require_root


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Kafka (Bitnami) via Helm OCI...")

    replicas = typer.prompt("Numero de brokers", default="3")
    disk_size = typer.prompt("Storage por broker", default="20Gi")

    # Bitnami charts migraram para OCI. Usamos a referencia OCI diretamente.
    chart_ref = "oci://registry-1.docker.io/bitnamicharts/kafka"

    values = [
        f"replicaCount={replicas}",
        "zookeeper.enabled=true",
        f"persistence.size={disk_size}",
        "metrics.kafka.enabled=true",
        "metrics.jmx.enabled=true",
    ]

    helm_upgrade_install(
        release="kafka",
        chart=chart_ref,
        namespace="kafka",
        repo=None,
        repo_url=None,
        ctx=ctx,
        values=values,
    )
