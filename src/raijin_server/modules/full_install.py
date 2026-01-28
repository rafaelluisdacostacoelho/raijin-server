"""Instalacao completa e automatizada do ambiente produtivo."""

import typer

from raijin_server.utils import ExecutionContext, require_root
from raijin_server.modules import (
    bootstrap,
    calico,
    essentials,
    firewall,
    grafana,
    hardening,
    kubernetes,
    loki,
    network,
    observability_dashboards,
    observability_ingress,
    prometheus,
    sanitize,
    traefik,
)


# Ordem de execucao dos modulos para instalacao completa
INSTALL_SEQUENCE = [
    ("sanitize", sanitize.run, "Limpeza total de instalacoes anteriores"),
    ("bootstrap", bootstrap.run, "Instalacao de ferramentas (helm, kubectl, containerd, etc.)"),
    ("essentials", essentials.run, "Pacotes essenciais e NTP"),
    ("hardening", hardening.run, "Seguranca do sistema (fail2ban, sysctl, auditd)"),
    ("network", network.run, "Configuracao de rede (IP fixo)"),
    ("firewall", firewall.run, "Firewall UFW"),
    ("kubernetes", kubernetes.run, "Cluster Kubernetes (kubeadm)"),
    ("calico", calico.run, "CNI Calico + NetworkPolicy"),
    ("prometheus", prometheus.run, "Monitoramento Prometheus"),
    ("grafana", grafana.run, "Dashboards Grafana"),
    ("loki", loki.run, "Logs centralizados Loki"),
    ("traefik", traefik.run, "Ingress Controller Traefik"),
    ("observability_ingress", observability_ingress.run, "Ingress seguro para Grafana/Prometheus/Alertmanager"),
    ("observability_dashboards", observability_dashboards.run, "Dashboards opinativos e alertas"),
]


def run(ctx: ExecutionContext) -> None:
    """Executa instalacao completa do ambiente produtivo."""
    require_root(ctx)

    typer.secho(
        "\n" + "=" * 60,
        fg=typer.colors.CYAN,
    )
    typer.secho(
        "  RAIJIN SERVER - Instalacao Completa Automatizada",
        fg=typer.colors.CYAN,
        bold=True,
    )
    typer.secho(
        "=" * 60 + "\n",
        fg=typer.colors.CYAN,
    )

    # Mostra sequencia de instalacao
    typer.echo("Sequencia de instalacao:")
    for i, (name, _, desc) in enumerate(INSTALL_SEQUENCE, 1):
        typer.echo(f"  {i:2}. {name:15} - {desc}")

    typer.echo("")

    if not ctx.dry_run:
        if not typer.confirm("Deseja continuar com a instalacao completa?", default=True):
            typer.echo("Instalacao cancelada.")
            raise typer.Exit(code=0)

    total = len(INSTALL_SEQUENCE)
    failed = []
    succeeded = []

    for i, (name, handler, desc) in enumerate(INSTALL_SEQUENCE, 1):
        typer.secho(
            f"\n{'='*60}",
            fg=typer.colors.CYAN,
        )
        typer.secho(
            f"[{i}/{total}] {name.upper()}: {desc}",
            fg=typer.colors.CYAN,
            bold=True,
        )
        typer.secho(
            f"{'='*60}\n",
            fg=typer.colors.CYAN,
        )

        try:
            handler(ctx)
            succeeded.append(name)
            typer.secho(f"✓ {name} concluido com sucesso", fg=typer.colors.GREEN)
        except KeyboardInterrupt:
            typer.secho(f"\n⚠ Instalacao interrompida pelo usuario no modulo '{name}'", fg=typer.colors.YELLOW)
            raise typer.Exit(code=130)
        except Exception as e:
            failed.append((name, str(e)))
            typer.secho(f"✗ {name} falhou: {e}", fg=typer.colors.RED)

            if not ctx.dry_run:
                if not typer.confirm("Continuar com os proximos modulos?", default=True):
                    break

    # Resumo final
    typer.echo("\n" + "=" * 60)
    typer.secho("RESUMO DA INSTALACAO", fg=typer.colors.CYAN, bold=True)
    typer.echo("=" * 60)

    if succeeded:
        typer.secho(f"\n✓ Modulos instalados com sucesso ({len(succeeded)}):", fg=typer.colors.GREEN)
        for name in succeeded:
            typer.echo(f"    - {name}")

    if failed:
        typer.secho(f"\n✗ Modulos com falha ({len(failed)}):", fg=typer.colors.RED)
        for name, error in failed:
            typer.echo(f"    - {name}: {error}")

    if not failed:
        typer.secho(
            "\n✓ INSTALACAO COMPLETA COM SUCESSO!",
            fg=typer.colors.GREEN,
            bold=True,
        )
        typer.echo("\nProximos passos:")
        typer.echo("  1. Verifique o cluster: kubectl get nodes")
        typer.echo("  2. Acesse Grafana: kubectl port-forward svc/grafana 3000:80 -n observability")
        typer.echo("  3. Adicione workers: kubeadm token create --print-join-command")
    else:
        typer.secho(
            f"\n⚠ Instalacao concluida com {len(failed)} erro(s). Verifique os logs.",
            fg=typer.colors.YELLOW,
            bold=True,
        )
