"""Gerenciador de instalacao e desinstalacao de modulos."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from raijin_server.utils import ExecutionContext, run_cmd, logger
from raijin_server.validators import (
    MODULE_DEPENDENCIES,
    get_reverse_dependencies,
    get_installed_dependents,
    check_uninstall_safety,
    check_module_dependencies,
)

console = Console()


# Mapeamento de modulos para suas funcoes de uninstall
# Sera populado dinamicamente pelo CLI
UNINSTALL_HANDLERS: Dict[str, Callable[[ExecutionContext], None]] = {}


def get_state_dir() -> Path:
    """Retorna diretorio de estado."""
    state_dir = Path(os.environ.get("RAIJIN_STATE_DIR", "/var/lib/raijin-server/state"))
    if state_dir.exists():
        return state_dir
    alt_dir = Path.home() / ".local/share/raijin-server/state"
    return alt_dir


def is_module_installed(module: str) -> bool:
    """Verifica se um modulo esta instalado (tem arquivo .done)."""
    state_dir = get_state_dir()
    state_file = state_dir / f"{module}.done"
    return state_file.exists()


def mark_module_uninstalled(module: str) -> None:
    """Remove marcador de instalacao do modulo."""
    state_dir = get_state_dir()
    state_file = state_dir / f"{module}.done"
    if state_file.exists():
        state_file.unlink()
        logger.info(f"Marcador de estado removido: {state_file}")


def get_module_status() -> Dict[str, bool]:
    """Retorna status de instalacao de todos os modulos."""
    from raijin_server.cli import MODULES
    
    status = {}
    for module in MODULES.keys():
        if module == "full_install":
            continue
        status[module] = is_module_installed(module)
    return status


def show_dependency_tree(module: str) -> None:
    """Exibe arvore de dependencias de um modulo."""
    console.print(f"\n[bold cyan]Arvore de dependencias para '{module}':[/bold cyan]")
    
    # Dependencias (o que este modulo precisa)
    deps = MODULE_DEPENDENCIES.get(module, [])
    if deps:
        console.print(f"\n[yellow]Requer (dependencias):[/yellow]")
        for dep in deps:
            installed = "✓" if is_module_installed(dep) else "✗"
            color = "green" if is_module_installed(dep) else "red"
            console.print(f"  [{color}]{installed}[/{color}] {dep}")
    else:
        console.print(f"\n[dim]Nenhuma dependencia[/dim]")
    
    # Dependentes (quem depende deste modulo)
    dependents = get_reverse_dependencies(module)
    if dependents:
        console.print(f"\n[yellow]Dependentes (quem usa este modulo):[/yellow]")
        for dep in dependents:
            installed = "✓" if is_module_installed(dep) else "○"
            color = "green" if is_module_installed(dep) else "dim"
            console.print(f"  [{color}]{installed}[/{color}] {dep}")
    else:
        console.print(f"\n[dim]Nenhum modulo depende deste[/dim]")


def show_uninstall_impact(module: str) -> Tuple[bool, List[str]]:
    """Mostra impacto da remocao e retorna se e seguro."""
    is_safe, affected, warning = check_uninstall_safety(module)
    
    if not is_safe:
        console.print(Panel(
            warning,
            title="⚠️  AVISO DE IMPACTO",
            border_style="yellow",
        ))
        
        # Mostra arvore de impacto detalhada
        table = Table(title="Modulos que serao afetados")
        table.add_column("Modulo", style="red")
        table.add_column("Status", style="yellow")
        table.add_column("Depende de", style="cyan")
        
        for mod in affected:
            deps = MODULE_DEPENDENCIES.get(mod, [])
            relevant_deps = [d for d in deps if d == module or d in affected]
            table.add_row(
                mod,
                "Instalado" if is_module_installed(mod) else "Nao instalado",
                ", ".join(relevant_deps)
            )
        
        console.print(table)
        console.print()
    
    return is_safe, affected


def uninstall_module(
    module: str,
    ctx: ExecutionContext,
    force: bool = False,
    cascade: bool = False,
) -> bool:
    """Desinstala um modulo com verificacao de seguranca.
    
    Args:
        module: Nome do modulo a desinstalar
        ctx: Contexto de execucao
        force: Ignora avisos de seguranca
        cascade: Remove tambem os modulos dependentes
        
    Returns:
        True se desinstalou com sucesso
    """
    if not is_module_installed(module):
        typer.secho(f"Modulo '{module}' nao esta instalado.", fg=typer.colors.YELLOW)
        return False
    
    # Verifica seguranca
    is_safe, affected = show_uninstall_impact(module)
    
    if not is_safe and not force:
        if cascade:
            # Desinstala dependentes primeiro (ordem reversa)
            console.print(f"\n[yellow]Modo cascade: removendo dependentes primeiro...[/yellow]")
            for dep in reversed(affected):
                if is_module_installed(dep):
                    console.print(f"\n[cyan]Removendo {dep}...[/cyan]")
                    uninstall_module(dep, ctx, force=True, cascade=False)
        else:
            confirm = typer.confirm(
                "\nDeseja continuar mesmo assim? (os modulos afetados podem parar de funcionar)",
                default=False,
            )
            if not confirm:
                typer.secho("Operacao cancelada.", fg=typer.colors.YELLOW)
                return False
    
    # Executa uninstall especifico se disponivel
    if module in UNINSTALL_HANDLERS:
        typer.echo(f"\nExecutando uninstall de '{module}'...")
        try:
            UNINSTALL_HANDLERS[module](ctx)
        except Exception as e:
            typer.secho(f"Erro durante uninstall: {e}", fg=typer.colors.RED)
            if not force:
                return False
    else:
        # Uninstall generico - apenas remove marcador
        typer.secho(
            f"Modulo '{module}' nao tem handler de uninstall especifico.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Apenas o marcador de estado sera removido.")
        typer.echo("Recursos no cluster podem precisar de remocao manual.")
    
    # Remove marcador de estado
    mark_module_uninstalled(module)
    typer.secho(f"✓ Modulo '{module}' marcado como desinstalado.", fg=typer.colors.GREEN)
    
    return True


def list_modules_status() -> None:
    """Lista todos os modulos e seus status."""
    from raijin_server.cli import MODULE_DESCRIPTIONS
    
    table = Table(title="Status dos Modulos Raijin")
    table.add_column("Modulo", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Dependencias")
    table.add_column("Descricao", style="dim")
    
    status = get_module_status()
    
    for module, installed in sorted(status.items()):
        status_icon = "[green]✓ Instalado[/green]" if installed else "[dim]○ Nao instalado[/dim]"
        deps = MODULE_DEPENDENCIES.get(module, [])
        deps_str = ", ".join(deps) if deps else "-"
        desc = MODULE_DESCRIPTIONS.get(module, "")[:40]
        if len(MODULE_DESCRIPTIONS.get(module, "")) > 40:
            desc += "..."
        
        table.add_row(module, status_icon, deps_str, desc)
    
    console.print(table)


def check_kubernetes_resource(resource_type: str, name: str, namespace: str = "") -> bool:
    """Verifica se um recurso Kubernetes existe."""
    cmd = ["kubectl", "get", resource_type, name]
    if namespace:
        cmd.extend(["-n", namespace])
    
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generic_helm_uninstall(release_name: str, namespace: str, ctx: ExecutionContext) -> bool:
    """Desinstala um release Helm de forma generica."""
    typer.echo(f"Removendo release Helm '{release_name}' do namespace '{namespace}'...")
    
    # Verifica se existe
    result = run_cmd(
        ["helm", "status", release_name, "-n", namespace],
        ctx,
        check=False,
    )
    
    if result.returncode != 0:
        typer.echo(f"Release '{release_name}' nao encontrado.")
        return False
    
    # Remove release
    result = run_cmd(
        ["helm", "uninstall", release_name, "-n", namespace],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        typer.secho(f"✓ Release '{release_name}' removido.", fg=typer.colors.GREEN)
        return True
    else:
        typer.secho(f"✗ Falha ao remover release '{release_name}'.", fg=typer.colors.RED)
        return False


def cleanup_namespace(namespace: str, ctx: ExecutionContext, wait: bool = True) -> bool:
    """Remove um namespace do Kubernetes."""
    typer.echo(f"Removendo namespace '{namespace}'...")
    
    result = run_cmd(
        ["kubectl", "delete", "namespace", namespace, "--ignore-not-found"],
        ctx,
        check=False,
    )
    
    if wait and result.returncode == 0:
        import time
        # Aguarda namespace ser removido
        deadline = time.time() + 60
        while time.time() < deadline:
            check = run_cmd(
                ["kubectl", "get", "namespace", namespace],
                ctx,
                check=False,
            )
            if check.returncode != 0:
                break
            time.sleep(5)
    
    return result.returncode == 0


def cleanup_crds(pattern: str, ctx: ExecutionContext) -> int:
    """Remove CRDs que correspondem ao padrao."""
    import subprocess
    
    # Lista CRDs
    result = subprocess.run(
        ["kubectl", "get", "crd", "-o", "name"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        return 0
    
    removed = 0
    for line in result.stdout.strip().split("\n"):
        if pattern in line:
            crd_name = line.replace("customresourcedefinition.apiextensions.k8s.io/", "")
            run_cmd(
                ["kubectl", "delete", "crd", crd_name, "--ignore-not-found"],
                ctx,
                check=False,
            )
            removed += 1
    
    return removed
