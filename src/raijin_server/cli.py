"""CLI principal do projeto Raijin Server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Optional

import subprocess

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from raijin_server import __version__
from raijin_server.modules import (
    apokolips_demo,
    bootstrap,
    calico,
    cert_manager,
    essentials,
    firewall,
    full_install,
    grafana,
    harness,
    hardening,
    istio,
    kafka,
    kong,
    kubernetes,
    loki,
    minio,
    network,
    observability_dashboards,
    observability_ingress,
    prometheus,
    secrets,
    sanitize,
    ssh_hardening,
    traefik,
    velero,
    vpn,
)
from raijin_server.utils import ExecutionContext, logger, active_log_file, available_log_files, page_text, ensure_tool
from raijin_server.validators import validate_system_requirements, check_module_dependencies
from raijin_server.healthchecks import run_health_check
from raijin_server.config import ConfigManager

app = typer.Typer(add_completion=False, help="Automacao de setup e hardening para Ubuntu Server")
console = Console()
STATE_DIR_CANDIDATES = [
    Path("/var/lib/raijin-server/state"),
    Path.home() / ".local/share/raijin-server/state",
]
EXIT_OPTION = "sair"
_STATE_DIR_CACHE: Optional[Path] = None

BANNER = r"""

      ___           ___                        ___                     ___     
     /\  \         /\  \          ___         /\  \        ___        /\__\    
    /::\  \       /::\  \        /\  \        \:\  \      /\  \      /::|  |   
   /:/\:\  \     /:/\:\  \       \:\  \   ___ /::\__\     \:\  \    /:|:|  |   
  /::\~\:\  \   /::\~\:\  \      /::\__\ /\  /:/\/__/     /::\__\  /:/|:|  |__ 
 /:/\:\ \:\__\ /:/\:\ \:\__\  __/:/\/__/ \:\/:/  /     __/:/\/__/ /:/ |:| /\__\
 \/_|::\/:/  / \/__\:\/:/  / /\/:/  /     \::/  /     /\/:/  /    \/__|:|/:/  /
    |:|::/  /       \::/  /  \::/__/       \/__/      \::/__/         |:/:/  / 
    |:|\/__/        /:/  /    \:\__\                   \:\__\         |::/  /  
    |:|  |         /:/  /      \/__/                    \/__/         /:/  /   
     \|__|         \/__/                                              \/__/    

"""

MODULES: Dict[str, Callable[[ExecutionContext], None]] = {
    "sanitize": sanitize.run,
    "bootstrap": bootstrap.run,
    "ssh_hardening": ssh_hardening.run,
    "hardening": hardening.run,
    "network": network.run,
    "essentials": essentials.run,
    "firewall": firewall.run,
    "vpn": vpn.run,
    "kubernetes": kubernetes.run,
    "calico": calico.run,
    "cert_manager": cert_manager.run,
    "istio": istio.run,
    "traefik": traefik.run,
    "kong": kong.run,
    "minio": minio.run,
    "prometheus": prometheus.run,
    "grafana": grafana.run,
    "observability_ingress": observability_ingress.run,
    "observability_dashboards": observability_dashboards.run,
    "apokolips_demo": apokolips_demo.run,
    "secrets": secrets.run,
    "loki": loki.run,
    "harness": harness.run,
    "velero": velero.run,
    "kafka": kafka.run,
    "full_install": full_install.run,
}

MODULE_DESCRIPTIONS: Dict[str, str] = {
    "sanitize": "Remove instalacoes antigas de Kubernetes e prepara ambiente",
    "bootstrap": "Instala ferramentas: helm, kubectl, istioctl, velero, containerd",
    "ssh_hardening": "Configura usuario dedicado, chaves e politicas de SSH",
    "hardening": "Ajustes de kernel, auditd, fail2ban",
    "network": "Netplan, hostname, DNS",
    "essentials": "Pacotes basicos, repos, utilitarios",
    "firewall": "Regras UFW padrao e serviços basicos",
    "vpn": "Provisiona WireGuard com cliente inicial",
    "kubernetes": "Instala kubeadm/kubelet/kubectl e inicializa cluster",
    "calico": "CNI Calico e politica default deny",
    "cert_manager": "Instala cert-manager e ClusterIssuer ACME",
    "istio": "Service mesh Istio via Helm",
    "traefik": "Ingress controller Traefik com TLS",
    "kong": "Ingress/Gateway Kong via Helm",
    "minio": "Objeto storage S3-compat via Helm",
    "prometheus": "Stack kube-prometheus",
    "grafana": "Dashboards e datasource Prometheus",
    "observability_ingress": "Ingress seguro com auth/TLS para Grafana/Prometheus/Alertmanager",
    "observability_dashboards": "Dashboards Grafana + alertas default Prometheus/Alertmanager",
    "apokolips_demo": "Landing page Apokolips para testar ingress externo",
    "secrets": "Instala sealed-secrets e external-secrets via Helm",
    "loki": "Logs centralizados Loki",
    "harness": "Delegate Harness via Helm",
    "velero": "Backup/restore de clusters",
    "kafka": "Cluster Kafka via OCI Helm",
    "full_install": "Instalacao completa e automatizada do ambiente",
}


def _capture_cmd(cmd: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip() or "(sem saida)"
        return (
            f"✗ {' '.join(cmd)}\n"
            f"{(result.stdout or '').strip()}\n{(result.stderr or '').strip()}".strip()
        )
    except Exception as exc:
        return f"✗ {' '.join(cmd)} -> {exc}"


def _run_module(ctx: typer.Context, name: str, skip_validation: bool = False) -> None:
    handler = MODULES.get(name)
    if handler is None:
        raise typer.BadParameter(f"Modulo '{name}' nao encontrado.")
    exec_ctx = ctx.obj or ExecutionContext()
    
    # Verifica dependencias do modulo
    if not skip_validation and not check_module_dependencies(name, exec_ctx):
        typer.secho(f"Execute primeiro os modulos dependentes antes de '{name}'", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    try:
        logger.info(f"Iniciando execucao do modulo: {name}")
        typer.secho(f"\n{'='*60}", fg=typer.colors.CYAN)
        typer.secho(f"Executando modulo: {name}", fg=typer.colors.CYAN, bold=True)
        typer.secho(f"{'='*60}\n", fg=typer.colors.CYAN)
        
        handler(exec_ctx)
        
        # Executa health check se disponivel
        if not exec_ctx.dry_run:
            typer.echo("\nExecutando health check...")
            health_ok = run_health_check(name, exec_ctx)
            if health_ok:
                _mark_completed(name)
                typer.secho(f"\n✓ Modulo '{name}' concluido com sucesso!", fg=typer.colors.GREEN, bold=True)
                logger.info(f"Modulo '{name}' concluido com sucesso")
            else:
                typer.secho(f"\n⚠ Modulo '{name}' executado mas health check falhou", fg=typer.colors.YELLOW, bold=True)
                logger.warning(f"Modulo '{name}' executado mas health check falhou")
        else:
            typer.secho(f"\n✓ Modulo '{name}' executado em modo dry-run", fg=typer.colors.YELLOW)
            
        # Mostra avisos e erros acumulados
        if exec_ctx.warnings:
            typer.secho(f"\nAvisos ({len(exec_ctx.warnings)}):", fg=typer.colors.YELLOW)
            for warn in exec_ctx.warnings:
                typer.echo(f"  ⚠ {warn}")
        if exec_ctx.errors:
            typer.secho(f"\nErros ({len(exec_ctx.errors)}):", fg=typer.colors.RED)
            for err in exec_ctx.errors:
                typer.echo(f"  ✗ {err}")
                
    except KeyboardInterrupt:
        logger.warning(f"Modulo '{name}' interrompido pelo usuario")
        typer.secho(f"\n\n⚠ Modulo '{name}' interrompido", fg=typer.colors.YELLOW)
        raise typer.Exit(code=130)
    except Exception as e:
        logger.error(f"Erro fatal no modulo '{name}': {e}", exc_info=True)
        typer.secho(f"\n✗ Erro fatal no modulo '{name}': {e}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)


def _print_banner() -> None:
    console.print(Panel.fit(BANNER, style="bold blue"))
    console.print("[bright_white]Automacao de setup e hardening para Ubuntu Server[/bright_white]\n")


def _select_state_dir() -> Path:
    global _STATE_DIR_CACHE
    if _STATE_DIR_CACHE is not None:
        return _STATE_DIR_CACHE

    override = os.environ.get("RAIJIN_STATE_DIR")
    if override:
        cand = Path(override).expanduser()
        cand.mkdir(parents=True, exist_ok=True)
        _STATE_DIR_CACHE = cand
        console.print(f"[cyan]Usando estado em {cand} (RAIJIN_STATE_DIR)[/cyan]")
        return cand

    for cand in STATE_DIR_CANDIDATES:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            test = cand / ".rwtest"
            test.touch()
            test.unlink()
            _STATE_DIR_CACHE = cand
            if cand != STATE_DIR_CANDIDATES[0]:
                console.print(f"[yellow]Estado gravado em {cand} (fallback por permissao)[/yellow]")
            return cand
        except Exception:
            continue

    fallback = Path("/tmp/raijin-state")
    fallback.mkdir(parents=True, exist_ok=True)
    console.print("[yellow]Usando fallback /tmp/raijin-state para marcar conclusao[/yellow]")
    _STATE_DIR_CACHE = fallback
    return fallback


def _state_file(name: str) -> Path:
    return _select_state_dir() / f"{name}.done"


def _mark_completed(name: str) -> None:
    try:
        path = _state_file(name)
        path.write_text("ok\n")
    except Exception:
        console.print("[yellow]Nao foi possivel registrar estado (permissao negada). Considere definir RAIJIN_STATE_DIR.[/yellow]")


def _is_completed(name: str) -> bool:
    return _state_file(name).exists()


def _render_menu(dry_run: bool) -> int:
    table = Table(
        title="Selecione um modulo para executar",
        header_style="bold white",
        box=box.ROUNDED,
        expand=True,
    )
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Status", style="green", no_wrap=True)
    table.add_column("Modulo", style="bold green")
    table.add_column("Descricao", style="white")
    for idx, name in enumerate(MODULES.keys(), start=1):
        desc = MODULE_DESCRIPTIONS.get(name, "")
        status = "[green]✔[/green]" if _is_completed(name) else "[dim]-[/dim]"
        table.add_row(f"{idx}", status, name, desc)

    exit_idx = len(MODULES) + 1
    table.add_row(
        f"{exit_idx}", "[red]↩[/red]", EXIT_OPTION, "Sair do menu",
    )

    mode_label = "[yellow]DRY-RUN[/yellow]" if dry_run else "[bold red]APLICAR[/bold red]"
    console.print(Panel.fit(f"Modo atual: {mode_label}  |  t = alternar modo  |  {EXIT_OPTION} = sair", style="dim"))
    console.print(table)
    return exit_idx


def _version_callback(value: bool) -> None:
    """Imprime a versao e encerra imediatamente."""

    if value:
        typer.echo(f"raijin-server {__version__}")
        raise typer.Exit()


def interactive_menu(ctx: typer.Context) -> None:
    exec_ctx = ctx.obj or ExecutionContext()
    current_dry_run = exec_ctx.dry_run
    _print_banner()
    console.print(
        Panel.fit(
            f"Use o numero, nome ou '{EXIT_OPTION}'.\nPressione t para alternar dry-run.",
            style="bold magenta",
        )
    )

    while True:
        exit_idx = _render_menu(current_dry_run)
        choice = Prompt.ask("Escolha", default=EXIT_OPTION).strip().lower()

        if choice in {"q", EXIT_OPTION}:
            return
        if choice == "t":
            current_dry_run = not current_dry_run
            exec_ctx.dry_run = current_dry_run
            continue

        if choice.isdigit():
            idx = int(choice)
            if idx == exit_idx:
                return
            if 1 <= idx <= len(MODULES):
                name = list(MODULES.keys())[idx - 1]
            else:
                console.print("[red]Opcao invalida[/red]")
                continue
        else:
            name = choice

        if name not in MODULES:
            console.print("[red]Opcao invalida[/red]")
            continue

        exec_ctx = ExecutionContext(dry_run=current_dry_run)
        ctx.obj = exec_ctx
        _run_module(ctx, name)
        # Loop continua e menu eh re-renderizado, refletindo status atualizado quando nao eh dry-run.


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    module: Optional[str] = typer.Option(None, "-m", "--module", help="Modulo a executar"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="Mostra comandos sem executa-los."),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Pula validacoes de pre-requisitos"),
    skip_root: bool = typer.Option(False, "--skip-root", help="Permite validar sem exigir root (nao recomendado)"),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="Mostra a versao do CLI e sai",
    ),
) -> None:
    """Mostra um menu simples quando nenhum subcomando e informado."""

    ctx.obj = ExecutionContext(dry_run=dry_run)

    # Executa validacoes de pre-requisitos
    if not skip_validation and not dry_run:
        if not validate_system_requirements(ctx.obj, skip_root=skip_root):
            typer.secho("\nAbortando devido a pre-requisitos nao atendidos.", fg=typer.colors.RED)
            typer.echo("Use --skip-validation para pular validacoes (nao recomendado).")
            raise typer.Exit(code=1)

    if ctx.invoked_subcommand:
        return
    if module:
        _run_module(ctx, module, skip_validation=skip_validation)
        return

    interactive_menu(ctx)


@app.command()
def menu(ctx: typer.Context) -> None:
    """Abre o menu interativo colorido."""

    interactive_menu(ctx)


@app.command()
def hardening(ctx: typer.Context) -> None:
    _run_module(ctx, "hardening")


@app.command(name="ssh-hardening")
def ssh_hardening_cmd(ctx: typer.Context) -> None:
    _run_module(ctx, "ssh_hardening")


@app.command()
def network(ctx: typer.Context) -> None:
    _run_module(ctx, "network")


@app.command()
def essentials(ctx: typer.Context) -> None:
    _run_module(ctx, "essentials")


@app.command()
def firewall(ctx: typer.Context) -> None:
    _run_module(ctx, "firewall")


@app.command()
def kubernetes(ctx: typer.Context) -> None:
    _run_module(ctx, "kubernetes")


@app.command()
def calico(ctx: typer.Context) -> None:
    _run_module(ctx, "calico")


@app.command()
def istio(ctx: typer.Context) -> None:
    _run_module(ctx, "istio")


@app.command()
def traefik(ctx: typer.Context) -> None:
    _run_module(ctx, "traefik")


@app.command()
def kong(ctx: typer.Context) -> None:
    _run_module(ctx, "kong")


@app.command()
def minio(ctx: typer.Context) -> None:
    _run_module(ctx, "minio")


@app.command()
def prometheus(ctx: typer.Context) -> None:
    _run_module(ctx, "prometheus")


@app.command()
def grafana(ctx: typer.Context) -> None:
    _run_module(ctx, "grafana")


@app.command(name="apokolips-demo")
def apokolips_demo_cmd(ctx: typer.Context) -> None:
    _run_module(ctx, "apokolips_demo")


@app.command(name="observability-ingress")
def observability_ingress_cmd(ctx: typer.Context) -> None:
    _run_module(ctx, "observability_ingress")


@app.command(name="observability-dashboards")
def observability_dashboards_cmd(ctx: typer.Context) -> None:
    _run_module(ctx, "observability_dashboards")


@app.command()
def loki(ctx: typer.Context) -> None:
    _run_module(ctx, "loki")


@app.command()
def harness(ctx: typer.Context) -> None:
    _run_module(ctx, "harness")


@app.command()
def velero(ctx: typer.Context) -> None:
    _run_module(ctx, "velero")


@app.command()
def kafka(ctx: typer.Context) -> None:
    _run_module(ctx, "kafka")


@app.command()
def vpn(ctx: typer.Context) -> None:
    _run_module(ctx, "vpn")


@app.command()
def sanitize(ctx: typer.Context) -> None:
    _run_module(ctx, "sanitize")


# ============================================================================
# Subcomandos Cert-Manager
# ============================================================================
cert_app = typer.Typer(help="Comandos para gerenciamento do cert-manager")
app.add_typer(cert_app, name="cert")


@cert_app.command(name="install")
def cert_install(ctx: typer.Context) -> None:
    """Instala cert-manager e configura ClusterIssuer interativamente."""
    _run_module(ctx, "cert_manager")


@cert_app.command(name="status")
def cert_status(ctx: typer.Context) -> None:
    """Exibe status detalhado do cert-manager, pods, webhook e certificados."""
    exec_ctx = ctx.obj or ExecutionContext()
    cert_manager.status(exec_ctx)


@cert_app.command(name="diagnose")
def cert_diagnose(ctx: typer.Context) -> None:
    """Executa diagnóstico completo para troubleshooting do cert-manager."""
    exec_ctx = ctx.obj or ExecutionContext()
    cert_manager.diagnose(exec_ctx)


@cert_app.command(name="list-certs")
def cert_list(ctx: typer.Context) -> None:
    """Lista todos os certificados no cluster."""
    import subprocess
    
    typer.secho("\n📜 Certificados no Cluster", fg=typer.colors.CYAN, bold=True)
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "certificates", "-A",
                "-o", "wide"
            ],
            capture_output=False,
            timeout=15,
        )
        if result.returncode != 0:
            typer.secho("Nenhum certificado encontrado ou erro ao listar.", fg=typer.colors.YELLOW)
    except Exception as e:
        typer.secho(f"Erro: {e}", fg=typer.colors.RED)


@cert_app.command(name="list-issuers")
def cert_list_issuers(ctx: typer.Context) -> None:
    """Lista todos os ClusterIssuers e Issuers."""
    import subprocess
    
    typer.secho("\n🔐 ClusterIssuers", fg=typer.colors.CYAN, bold=True)
    try:
        subprocess.run(
            ["kubectl", "get", "clusterissuers", "-o", "wide"],
            timeout=15,
        )
    except Exception:
        pass
    
    typer.secho("\n🔐 Issuers (por namespace)", fg=typer.colors.CYAN, bold=True)
    try:
        subprocess.run(
            ["kubectl", "get", "issuers", "-A", "-o", "wide"],
            timeout=15,
        )
    except Exception:
        pass


# ============================================================================
# Ferramentas de Depuração / Logs
# ============================================================================
debug_app = typer.Typer(help="Ferramentas de depuracao e investigacao de logs")
app.add_typer(debug_app, name="debug")


@debug_app.command(name="logs")
def debug_logs(
    lines: int = typer.Option(200, "--lines", "-n", help="Quantidade de linhas ao ler"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Segue o log com tail -F"),
    pager: bool = typer.Option(True, "--pager/--no-pager", help="Exibe com less"),
) -> None:
    """Mostra logs do raijin-server com opcao de follow."""

    logs = available_log_files()
    if not logs:
        typer.secho("Nenhum log encontrado", fg=typer.colors.YELLOW)
        return

    main_log = active_log_file()
    typer.echo(f"Log ativo: {main_log}")

    if follow:
        subprocess.run(["tail", "-n", str(lines), "-F", str(main_log)])
        return

    chunks = []
    for path in logs:
        try:
            data = path.read_text()
        except Exception as exc:
            data = f"[erro ao ler {path}: {exc}]"
        chunks.append(f"===== {path} =====\n{data}")

    output = "\n\n".join(chunks)
    if pager:
        page_text(output)
    else:
        typer.echo(output)


@debug_app.command(name="kube")
def debug_kube(
    ctx: typer.Context,
    events: int = typer.Option(200, "--events", "-e", help="Quantas linhas finais de eventos exibir"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Filtra pods/eventos por namespace"),
    pager: bool = typer.Option(True, "--pager/--no-pager", help="Exibe com less"),
) -> None:
    """Snapshot rapido de nodes, pods e eventos do cluster."""

    exec_ctx = ctx.obj or ExecutionContext()
    ensure_tool("kubectl", exec_ctx)

    sections = []
    sections.append(("kubectl get nodes -o wide", _capture_cmd(["kubectl", "get", "nodes", "-o", "wide"])))

    pods_cmd: list[str] = ["kubectl", "get", "pods"]
    if namespace:
        pods_cmd.extend(["-n", namespace])
    else:
        pods_cmd.append("-A")
    pods_cmd.extend(["-o", "wide"])
    sections.append(("kubectl get pods", _capture_cmd(pods_cmd)))

    events_cmd: list[str] = ["kubectl", "get", "events"]
    if namespace:
        events_cmd.extend(["-n", namespace])
    else:
        events_cmd.append("-A")
    events_cmd.extend(["--sort-by=.lastTimestamp"])
    events_output = _capture_cmd(events_cmd)
    if events_output and events > 0:
        events_output = "\n".join(events_output.splitlines()[-events:])
    sections.append(("kubectl get events", events_output))

    combined = "\n\n".join([f"[{title}]\n{body}" for title, body in sections])
    if pager:
        page_text(combined)
    else:
        typer.echo(combined)


@debug_app.command(name="journal")
def debug_journal(
    ctx: typer.Context,
    service: str = typer.Option("kubelet", "--service", "-s", help="Unidade systemd para inspecionar"),
    lines: int = typer.Option(200, "--lines", "-n", help="Linhas a exibir"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Segue o journal em tempo real"),
    pager: bool = typer.Option(True, "--pager/--no-pager", help="Exibe com less"),
) -> None:
    """Mostra logs de services (ex.: kubelet) via journalctl."""

    exec_ctx = ctx.obj or ExecutionContext()
    ensure_tool("journalctl", exec_ctx)

    cmd = ["journalctl", "-u", service, "-n", str(lines)]
    if follow:
        cmd.append("-f")
        subprocess.run(cmd)
        return

    cmd.append("--no-pager")
    output = _capture_cmd(cmd, timeout=60)
    if lines > 0:
        output = "\n".join(output.splitlines()[-lines:])

    text = f"[journalctl -u {service} -n {lines}]\n{output}"
    if pager:
        page_text(text)
    else:
        typer.echo(text)


# ============================================================================
# Comandos Existentes
# ============================================================================


@app.command(name="bootstrap")
def bootstrap_cmd(ctx: typer.Context) -> None:
    """Instala todas as ferramentas necessarias: helm, kubectl, istioctl, velero, containerd."""
    _run_module(ctx, "bootstrap")


@app.command(name="full-install")
def full_install_cmd(
    ctx: typer.Context,
    steps: Optional[str] = typer.Option(None, "--steps", help="Lista de modulos, separado por virgula"),
    confirm_each: bool = typer.Option(False, "--confirm-each", help="Pedir confirmacao antes de cada modulo"),
    debug_mode: bool = typer.Option(False, "--debug-mode", help="Habilita snapshots e diagnose pos-modulo"),
    snapshots: bool = typer.Option(False, "--snapshots", help="Habilita snapshots de cluster apos cada modulo"),
    post_diagnose: bool = typer.Option(False, "--post-diagnose", help="Executa diagnose pos-modulo quando disponivel"),
    select_steps: bool = typer.Option(False, "--select-steps", help="Pergunta quais modulos executar antes de iniciar"),
) -> None:
    """Executa instalacao completa e automatizada do ambiente de producao."""
    exec_ctx = ctx.obj or ExecutionContext()
    if steps:
        exec_ctx.selected_steps = [s.strip() for s in steps.split(",") if s.strip()]
    exec_ctx.interactive_steps = select_steps
    exec_ctx.confirm_each_step = confirm_each
    exec_ctx.debug_snapshots = debug_mode or snapshots or exec_ctx.debug_snapshots
    exec_ctx.post_diagnose = debug_mode or post_diagnose or exec_ctx.post_diagnose
    ctx.obj = exec_ctx
    _run_module(ctx, "full_install")


@app.command()
def version() -> None:
    """Mostra a versao do CLI."""

    typer.echo(f"raijin-server {__version__}")


@app.command()
def generate_config(output: str = typer.Option("raijin-config.yaml", "--output", "-o", help="Arquivo de saida")) -> None:
    """Gera template de configuracao YAML/JSON."""
    
    ConfigManager.create_template(output)


@app.command()
def validate(skip_root: bool = typer.Option(False, "--skip-root", help="Pula validacao de root")) -> None:
    """Valida pre-requisitos do sistema sem executar modulos."""
    
    ctx = ExecutionContext(dry_run=False)
    if validate_system_requirements(ctx, skip_root=skip_root):
        typer.secho("\n✓ Sistema validado com sucesso!", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho("\n✗ Sistema nao atende pre-requisitos", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)


def main_entrypoint() -> None:
    """Ponto de entrada para console_scripts."""

    app(prog_name="raijin-server")


if __name__ == "__main__":
    main_entrypoint()