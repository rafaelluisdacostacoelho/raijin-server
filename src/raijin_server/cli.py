"""CLI principal do projeto Raijin Server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from raijin_server import __version__
from raijin_server.modules import (
    calico,
    essentials,
    firewall,
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
    prometheus,
    traefik,
    velero,
)
from raijin_server.utils import ExecutionContext

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
    "hardening": hardening.run,
    "network": network.run,
    "essentials": essentials.run,
    "firewall": firewall.run,
    "kubernetes": kubernetes.run,
    "calico": calico.run,
    "istio": istio.run,
    "traefik": traefik.run,
    "kong": kong.run,
    "minio": minio.run,
    "prometheus": prometheus.run,
    "grafana": grafana.run,
    "loki": loki.run,
    "harness": harness.run,
    "velero": velero.run,
    "kafka": kafka.run,
}

MODULE_DESCRIPTIONS: Dict[str, str] = {
    "hardening": "Ajustes de kernel, auditd, fail2ban",
    "network": "Netplan, hostname, DNS",
    "essentials": "Pacotes basicos, repos, utilitarios",
    "firewall": "Regras UFW padrao e serviços basicos",
    "kubernetes": "Instala kubeadm/kubelet/kubectl e inicializa cluster",
    "calico": "CNI Calico e politica default deny",
    "istio": "Service mesh Istio via Helm",
    "traefik": "Ingress controller Traefik com TLS",
    "kong": "Ingress/Gateway Kong via Helm",
    "minio": "Objeto storage S3-compat via Helm",
    "prometheus": "Stack kube-prometheus",
    "grafana": "Dashboards e datasource Prometheus",
    "loki": "Logs centralizados Loki",
    "harness": "Delegate Harness via Helm",
    "velero": "Backup/restore de clusters",
    "kafka": "Cluster Kafka via OCI Helm",
}


def _run_module(ctx: typer.Context, name: str) -> None:
    handler = MODULES.get(name)
    if handler is None:
        raise typer.BadParameter(f"Modulo '{name}' nao encontrado.")
    exec_ctx = ctx.obj or ExecutionContext()
    handler(exec_ctx)
    if not exec_ctx.dry_run:
        _mark_completed(name)


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
    console.print(f"[yellow]Usando fallback /tmp/raijin-state para marcar conclusao[/yellow]")
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
) -> None:
    """Mostra um menu simples quando nenhum subcomando e informado."""

    ctx.obj = ExecutionContext(dry_run=dry_run)

    if ctx.invoked_subcommand:
        return
    if module:
        _run_module(ctx, module)
        return

    interactive_menu(ctx)


@app.command()
def menu(ctx: typer.Context) -> None:
    """Abre o menu interativo colorido."""

    interactive_menu(ctx)


@app.command()
def hardening(ctx: typer.Context) -> None:
    _run_module(ctx, "hardening")


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
def version() -> None:
    """Mostra a versao do CLI."""

    typer.echo(f"raijin-server {__version__}")


def main_entrypoint() -> None:
    """Ponto de entrada para console_scripts."""

    app(prog_name="raijin-server")


if __name__ == "__main__":
    main_entrypoint()