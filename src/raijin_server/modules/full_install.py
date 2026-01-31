"""Instalacao completa e automatizada do ambiente produtivo."""

import os
import subprocess
from typing import List

import typer

from raijin_server.utils import ExecutionContext, require_root
from raijin_server.healthchecks import run_health_check
from raijin_server.modules import (
    bootstrap,
    calico,
    cert_manager,
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
    secrets,
    sanitize,
    traefik,
)


def _cert_manager_install_only(ctx: ExecutionContext) -> None:
    """Wrapper para instalar cert-manager sem interação."""
    if not cert_manager.install_only(ctx):
        raise RuntimeError("Falha na instalação do cert-manager")
    
    # Cria issuer HTTP01 padrão para staging (teste) e produção
    # O usuário pode criar issuers adicionais depois com 'raijin-server cert install'
    email = os.environ.get("RAIJIN_ACME_EMAIL", "")
    if email and "@" in email:
        typer.secho("\n📜 Criando ClusterIssuers padrão...", fg=typer.colors.CYAN)
        
        # Cria issuer de staging (para testes)
        cert_manager.create_issuer(
            ctx,
            name="letsencrypt-staging",
            email=email,
            challenge_type="http01",
            staging=True,
            ingress_class="traefik",
        )
        
        # Cria issuer de produção
        cert_manager.create_issuer(
            ctx,
            name="letsencrypt-prod",
            email=email,
            challenge_type="http01",
            staging=False,
            ingress_class="traefik",
        )
        
        typer.secho("✓ ClusterIssuers 'letsencrypt-staging' e 'letsencrypt-prod' criados", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "ℹ Para criar ClusterIssuers automaticamente, defina RAIJIN_ACME_EMAIL",
            fg=typer.colors.YELLOW,
        )
        typer.secho(
            "  Exemplo: export RAIJIN_ACME_EMAIL=admin@seudominio.com",
            fg=typer.colors.YELLOW,
        )


def _confirm_colored(message: str, default: bool = True) -> bool:
    """Confirmação com destaque visual."""
    styled = typer.style(message, fg=typer.colors.YELLOW, bold=True)
    return typer.confirm(styled, default=default)


def _select_steps_interactively() -> List[str] | None:
    typer.secho("Selecione passos (separados por vírgula) ou ENTER para todos:", fg=typer.colors.CYAN)
    typer.echo("Exemplo: kubernetes,calico,cert_manager,traefik")
    answer = typer.prompt("Passos", default="").strip()
    if not answer:
        return None
    steps = [s.strip() for s in answer.split(",") if s.strip()]
    return steps or None


def _kube_snapshot(ctx: ExecutionContext, events: int = 100, namespace: str | None = None) -> None:
    """Coleta snapshot rápido de cluster para debug (best-effort)."""
    cmds = []
    cmds.append(["kubectl", "get", "nodes", "-o", "wide"])

    pods_cmd = ["kubectl", "get", "pods"]
    if namespace:
        pods_cmd += ["-n", namespace]
    else:
        pods_cmd.append("-A")
    pods_cmd += ["-o", "wide"]
    cmds.append(pods_cmd)

    events_cmd = ["kubectl", "get", "events"]
    if namespace:
        events_cmd += ["-n", namespace]
    else:
        events_cmd.append("-A")
    events_cmd += ["--sort-by=.lastTimestamp"]
    cmds.append(events_cmd)

    typer.secho("\n[DEBUG] Snapshot do cluster", fg=typer.colors.CYAN)
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            typer.echo(f"$ {' '.join(cmd)}")
            if result.stdout:
                lines = result.stdout.strip().splitlines()
                if cmd is events_cmd:
                    lines = lines[-events:]
                typer.echo("\n".join(lines))
            elif result.stderr:
                typer.echo(result.stderr.strip())
        except Exception as exc:
            typer.secho(f"(snapshot falhou: {exc})", fg=typer.colors.YELLOW)


def _run_cmd(title: str, cmd: List[str], ctx: ExecutionContext, tail: int | None = None) -> None:
    """Executa comando kubectl/helm best-effort para diagnosticos rapidos."""
    typer.secho(f"\n[diagnose] {title}", fg=typer.colors.CYAN)
    if ctx.dry_run:
        typer.echo("[dry-run] comando nao executado")
        return

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        typer.echo(f"$ {' '.join(cmd)}")
        output = result.stdout.strip() or result.stderr.strip()
        if output:
            lines = output.splitlines()
            if tail:
                lines = lines[-tail:]
            typer.echo("\n".join(lines))
        else:
            typer.echo("(sem saida)")
    except Exception as exc:
        typer.secho(f"(falha ao executar: {exc})", fg=typer.colors.YELLOW)


def _diag_namespace(ns: str, ctx: ExecutionContext, tail_events: int = 50) -> None:
    _run_cmd(f"Pods em {ns}", ["kubectl", "get", "pods", "-n", ns, "-o", "wide"], ctx)
    _run_cmd(f"Services em {ns}", ["kubectl", "get", "svc", "-n", ns], ctx)
    _run_cmd(f"Deployments em {ns}", ["kubectl", "get", "deploy", "-n", ns], ctx)
    _run_cmd(
        f"Eventos em {ns}",
        ["kubectl", "get", "events", "-n", ns, "--sort-by=.lastTimestamp"],
        ctx,
        tail=tail_events,
    )


def _diag_calico(ctx: ExecutionContext) -> None:
    ns = "kube-system"
    _run_cmd("Calico DaemonSets", ["kubectl", "get", "ds", "-n", ns, "-o", "wide"], ctx)
    _run_cmd("Calico pods", ["kubectl", "get", "pods", "-n", ns, "-l", "k8s-app=calico-node", "-o", "wide"], ctx)
    _run_cmd("Calico typha", ["kubectl", "get", "pods", "-n", ns, "-l", "k8s-app=calico-typha", "-o", "wide"], ctx)
    _run_cmd("Calico events", ["kubectl", "get", "events", "-n", ns, "--sort-by=.lastTimestamp"], ctx, tail=50)


def _diag_secrets(ctx: ExecutionContext) -> None:
    _diag_namespace("kube-system", ctx)
    _diag_namespace("external-secrets", ctx)


def _diag_prometheus(ctx: ExecutionContext) -> None:
    ns = "observability"
    _run_cmd("Prometheus pods", ["kubectl", "get", "pods", "-n", ns, "-l", "app.kubernetes.io/name=prometheus"], ctx)
    _diag_namespace(ns, ctx)


def _diag_grafana(ctx: ExecutionContext) -> None:
    ns = "observability"
    _run_cmd("Grafana svc", ["kubectl", "get", "svc", "-n", ns, "-l", "app.kubernetes.io/name=grafana"], ctx)
    _diag_namespace(ns, ctx)


def _diag_loki(ctx: ExecutionContext) -> None:
    ns = "observability"
    _run_cmd("Loki statefulsets", ["kubectl", "get", "sts", "-n", ns, "-l", "app.kubernetes.io/name=loki"], ctx)
    _diag_namespace(ns, ctx)


def _diag_traefik(ctx: ExecutionContext) -> None:
    ns = "traefik"
    _run_cmd("Traefik ingress", ["kubectl", "get", "ingress", "-n", ns], ctx)
    _diag_namespace(ns, ctx)


def _diag_observability_ingress(ctx: ExecutionContext) -> None:
    ns = "observability"
    _run_cmd("Ingress objects", ["kubectl", "get", "ingress", "-n", ns], ctx)
    _diag_namespace(ns, ctx)


def _diag_observability_dashboards(ctx: ExecutionContext) -> None:
    ns = "observability"
    _run_cmd("ConfigMaps dashboards", ["kubectl", "get", "configmap", "-n", ns, "-l", "raijin/dashboards=true"], ctx)
    _diag_namespace(ns, ctx)


def _diag_minio(ctx: ExecutionContext) -> None:
    ns = "minio"
    _diag_namespace(ns, ctx)


def _diag_kafka(ctx: ExecutionContext) -> None:
    ns = "kafka"
    _run_cmd("Kafka pods", ["kubectl", "get", "pods", "-n", ns, "-o", "wide"], ctx)
    _diag_namespace(ns, ctx)


def _diag_velero(ctx: ExecutionContext) -> None:
    ns = "velero"
    _diag_namespace(ns, ctx)


def _diag_kong(ctx: ExecutionContext) -> None:
    ns = "kong"
    _diag_namespace(ns, ctx)


DIAG_HANDLERS = {
    "cert_manager": cert_manager.diagnose,
    "calico": _diag_calico,
    "secrets": _diag_secrets,
    "prometheus": _diag_prometheus,
    "grafana": _diag_grafana,
    "loki": _diag_loki,
    "traefik": _diag_traefik,
    "observability_ingress": _diag_observability_ingress,
    "observability_dashboards": _diag_observability_dashboards,
    "minio": _diag_minio,
    "kafka": _diag_kafka,
    "velero": _diag_velero,
    "kong": _diag_kong,
}


def _maybe_diagnose(name: str, ctx: ExecutionContext) -> None:
    try:
        if name in DIAG_HANDLERS:
            DIAG_HANDLERS[name](ctx)
            return

        # fallback: health check se existir
        ok = run_health_check(name, ctx)
        if ok:
            typer.secho(f"[diagnose] {name}: OK", fg=typer.colors.GREEN)
        else:
            typer.secho(f"[diagnose] {name}: falhou", fg=typer.colors.YELLOW)
    except Exception as exc:
        typer.secho(f"[diagnose] {name} falhou: {exc}", fg=typer.colors.YELLOW)


# Ordem de execucao dos modulos para instalacao completa
# Modulos marcados com skip_env podem ser pulados via variavel de ambiente
INSTALL_SEQUENCE = [
    ("sanitize", sanitize.run, "Limpeza total de instalacoes anteriores", None),
    ("bootstrap", bootstrap.run, "Instalacao de ferramentas (helm, kubectl, containerd, etc.)", None),
    ("essentials", essentials.run, "Pacotes essenciais e NTP", None),
    ("hardening", hardening.run, "Seguranca do sistema (fail2ban, sysctl, auditd)", None),
    ("network", network.run, "Configuracao de rede (IP fixo) - OPCIONAL", "RAIJIN_SKIP_NETWORK"),
    ("firewall", firewall.run, "Firewall UFW", None),
    ("kubernetes", kubernetes.run, "Cluster Kubernetes (kubeadm)", None),
    ("calico", calico.run, "CNI Calico + NetworkPolicy", None),
    ("cert_manager", _cert_manager_install_only, "cert-manager (instalacao base)", None),
    ("secrets", secrets.run, "Sealed-Secrets + External-Secrets", None),
    ("prometheus", prometheus.run, "Monitoramento Prometheus", None),
    ("grafana", grafana.run, "Dashboards Grafana", None),
    ("loki", loki.run, "Logs centralizados Loki", None),
    ("traefik", traefik.run, "Ingress Controller Traefik", None),
    ("observability_ingress", observability_ingress.run, "Ingress seguro para Grafana/Prometheus/Alertmanager", None),
    ("observability_dashboards", observability_dashboards.run, "Dashboards opinativos e alertas", None),
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

    steps_override = ctx.selected_steps
    if steps_override is None and ctx.interactive_steps:
        steps_override = _select_steps_interactively()

    # Debug/diagnose menu simples
    if not ctx.debug_snapshots and not ctx.post_diagnose:
        typer.secho("Ativar modo debug (snapshots + diagnose pos-modulo)?", fg=typer.colors.YELLOW)
        if typer.confirm("Habilitar debug?", default=False):
            ctx.debug_snapshots = True
            ctx.post_diagnose = True

    # Mostra sequencia de instalacao
    typer.echo("Sequencia de instalacao:")
    for i, (name, _, desc, skip_env) in enumerate(INSTALL_SEQUENCE, 1):
        suffix = ""
        if skip_env and os.environ.get(skip_env, "").strip() in ("1", "true", "yes"):
            suffix = " [SKIP]"
        if steps_override and name not in steps_override:
            suffix = " [IGNORADO]"
        typer.echo(f"  {i:2}. {name:25} - {desc}{suffix}")

    typer.echo("")
    typer.secho(
        "Nota: O modulo 'network' eh OPCIONAL se o IP fixo ja foi configurado\n"
        "      pelo provedor ISP ou durante instalacao do SO.\n"
        "      Set RAIJIN_SKIP_NETWORK=1 para pular automaticamente.",
        fg=typer.colors.YELLOW,
    )
    typer.echo("")

    if not ctx.dry_run:
        if not _confirm_colored("Deseja continuar com a instalacao completa?", default=True):
            typer.echo("Instalacao cancelada.")
            raise typer.Exit(code=0)

    total = len(INSTALL_SEQUENCE)
    failed = []
    succeeded = []
    skipped = []

    cluster_ready = False

    for i, (name, handler, desc, skip_env) in enumerate(INSTALL_SEQUENCE, 1):
        if steps_override and name not in steps_override:
            skipped.append(name)
            typer.secho(f"⏭ {name} ignorado (fora da lista selecionada)", fg=typer.colors.YELLOW)
            continue

        # Verifica se modulo deve ser pulado via env
        if skip_env and os.environ.get(skip_env, "").strip() in ("1", "true", "yes"):
            skipped.append(name)
            typer.secho(f"⏭ {name} pulado via {skip_env}=1", fg=typer.colors.YELLOW)
            continue

        if ctx.confirm_each_step:
            if not _confirm_colored(f"Executar modulo '{name}' agora?", default=True):
                skipped.append(name)
                continue

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

            if name == "kubernetes":
                cluster_ready = True

            if ctx.post_diagnose and cluster_ready:
                _maybe_diagnose(name, ctx)

            if ctx.debug_snapshots and cluster_ready:
                _kube_snapshot(ctx, events=80)
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

    if skipped:
        typer.secho(f"\n⏭ Modulos pulados ({len(skipped)}):", fg=typer.colors.YELLOW)
        for name in skipped:
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
