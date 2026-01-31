"""Deploy do Apache Kafka via Helm (Bitnami OCI) - production-ready."""

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


def _check_existing_kafka(ctx: ExecutionContext) -> bool:
    """Verifica se existe instalacao do Kafka."""
    result = run_cmd(
        ["helm", "status", "kafka", "-n", "kafka"],
        ctx,
        check=False,
    )
    return result.returncode == 0


def _uninstall_kafka(ctx: ExecutionContext) -> None:
    """Remove instalacao anterior do Kafka."""
    typer.echo("Removendo instalacao anterior do Kafka...")
    
    run_cmd(
        ["helm", "uninstall", "kafka", "-n", "kafka"],
        ctx,
        check=False,
    )
    
    remove_data = typer.confirm("Remover PVCs (dados persistentes)?", default=False)
    if remove_data:
        run_cmd(
            ["kubectl", "-n", "kafka", "delete", "pvc", "-l", "app.kubernetes.io/name=kafka"],
            ctx,
            check=False,
        )
        run_cmd(
            ["kubectl", "-n", "kafka", "delete", "pvc", "-l", "app.kubernetes.io/name=zookeeper"],
            ctx,
            check=False,
        )
    
    time.sleep(5)


def _wait_for_kafka_ready(ctx: ExecutionContext, timeout: int = 300) -> bool:
    """Aguarda pods do Kafka ficarem Ready."""
    typer.echo("Aguardando pods do Kafka ficarem Ready...")
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        result = run_cmd(
            [
                "kubectl", "-n", "kafka", "get", "pods",
                "-l", "app.kubernetes.io/name=kafka",
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
                    typer.secho("  Kafka Ready.", fg=typer.colors.GREEN)
                    return True
        
        time.sleep(10)
    
    typer.secho("  Timeout aguardando Kafka.", fg=typer.colors.YELLOW)
    return False


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Instalando Kafka (Bitnami) via Helm OCI...")

    # Prompt opcional de limpeza
    if _check_existing_kafka(ctx):
        cleanup = typer.confirm(
            "Instalacao anterior do Kafka detectada. Limpar antes de reinstalar?",
            default=False,
        )
        if cleanup:
            _uninstall_kafka(ctx)

    replicas = typer.prompt("Numero de brokers Kafka", default="1")
    zk_replicas = typer.prompt("Numero de replicas Zookeeper", default="1")
    disk_size = typer.prompt("Storage por broker", default="20Gi")
    zk_disk_size = typer.prompt("Storage por Zookeeper", default="10Gi")

    node_name = _detect_node_name(ctx)

    values_yaml = f"""replicaCount: {replicas}
zookeeper:
  enabled: true
  replicaCount: {zk_replicas}
  persistence:
    enabled: true
    size: {zk_disk_size}
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  nodeSelector:
    kubernetes.io/hostname: {node_name}
persistence:
  enabled: true
  size: {disk_size}
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
  - key: node-role.kubernetes.io/master
    operator: Exists
    effect: NoSchedule
nodeSelector:
  kubernetes.io/hostname: {node_name}
metrics:
  kafka:
    enabled: true
  jmx:
    enabled: true
  serviceMonitor:
    enabled: true
    namespace: kafka
resources:
  requests:
    memory: 512Mi
    cpu: 250m
  limits:
    memory: 2Gi
"""

    values_path = Path("/tmp/raijin-kafka-values.yaml")
    write_file(values_path, values_yaml, ctx)

    run_cmd(["kubectl", "create", "namespace", "kafka"], ctx, check=False)

    # Bitnami charts migraram para OCI. Usamos a referencia OCI diretamente.
    chart_ref = "oci://registry-1.docker.io/bitnamicharts/kafka"

    helm_upgrade_install(
        release="kafka",
        chart=chart_ref,
        namespace="kafka",
        repo=None,
        repo_url=None,
        ctx=ctx,
        values=[],
        extra_args=["-f", str(values_path)],
    )

    if not ctx.dry_run:
        _wait_for_kafka_ready(ctx)

    typer.secho("\n✓ Kafka instalado com sucesso.", fg=typer.colors.GREEN, bold=True)
    typer.echo("\nPara conectar ao Kafka de dentro do cluster:")
    typer.echo("  kafka.kafka.svc.cluster.local:9092")
    typer.echo("\nPara port-forward local:")
    typer.echo("  kubectl -n kafka port-forward svc/kafka 9092:9092")
    typer.echo("\nPara criar um topic de teste:")
    typer.echo("  kubectl -n kafka exec -it kafka-0 -- kafka-topics.sh --create --topic test --bootstrap-server localhost:9092")
