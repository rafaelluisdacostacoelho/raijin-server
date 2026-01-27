"""Utilitarios compartilhados para execucao dos modulos."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

import typer


@dataclass
class ExecutionContext:
    """Contexto de execucao compartilhado entre modulos."""

    dry_run: bool = False
    assume_yes: bool = True


def _format_cmd(cmd: Sequence[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(shlex.quote(str(part)) for part in cmd)


def run_cmd(
    cmd: Sequence[str] | str,
    ctx: ExecutionContext,
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    check: bool = True,
    use_shell: bool = False,
    mask_output: bool = False,
    display_override: str | None = None,
) -> None:
    """Executa comando exibindo (ou mascarando) a linha usada.

    Quando `dry_run` esta ativo, apenas mostra a linha sem executar.
    """

    display = display_override or _format_cmd(cmd)
    prefix = "[dry-run] " if ctx.dry_run else ""
    if mask_output:
        typer.echo(f"{prefix}[masked] comando executado (argumentos sensiveis ocultos)")
    else:
        typer.echo(f"{prefix}$ {display}")

    if ctx.dry_run:
        return

    merged_env: MutableMapping[str, str] = os.environ.copy()
    if env:
        merged_env.update(env)

    subprocess.run(cmd, shell=use_shell, check=check, cwd=cwd, env=merged_env)


def require_root(ctx: ExecutionContext) -> None:
    """Encerra se o usuario atual nao for root."""

    if ctx.dry_run:
        typer.echo("[dry-run] Validacao de root ignorada.")
        return
    if os.geteuid() != 0:
        typer.secho("Este comando precisa ser executado como root (sudo).", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def ensure_tool(name: str, ctx: ExecutionContext, install_hint: str = "") -> None:
    """Valida que um binario esta disponivel no PATH (ignora quando dry-run)."""

    if ctx.dry_run:
        return
    if shutil.which(name) is None:
        hint = f" {install_hint}" if install_hint else ""
        typer.secho(f"Ferramenta '{name}' nao encontrada.{hint}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def apt_update(ctx: ExecutionContext) -> None:
    run_cmd(["apt-get", "update"], ctx)


def apt_install(packages: Iterable[str], ctx: ExecutionContext) -> None:
    pkgs = list(packages)
    if not pkgs:
        return
    run_cmd(
        ["apt-get", "install", "-y", *pkgs],
        ctx,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )


def enable_service(name: str, ctx: ExecutionContext) -> None:
    run_cmd(["systemctl", "enable", "--now", name], ctx)


def write_file(path: Path, content: str, ctx: ExecutionContext, *, mode: int = 0o644) -> None:
    """Escreve conteudo em arquivo respeitando dry-run."""

    if ctx.dry_run:
        typer.echo(f"[dry-run] escrever {path} (mode {oct(mode)}):\n{content}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.chmod(path, mode)
    typer.echo(f"Arquivo escrito: {path}")


def helm_repo_add(name: str, url: str, ctx: ExecutionContext) -> None:
    run_cmd(["helm", "repo", "add", name, url], ctx)


def helm_repo_update(ctx: ExecutionContext) -> None:
    run_cmd(["helm", "repo", "update"], ctx)


def helm_upgrade_install(
    release: str,
    chart: str,
    namespace: str,
    ctx: ExecutionContext,
    *,
    repo: str | None = None,
    repo_url: str | None = None,
    values: list[str] | None = None,
    create_namespace: bool = True,
    extra_args: list[str] | None = None,
) -> None:
    """Executa helm upgrade --install com opcoes comuns."""

    ensure_tool("helm", ctx, install_hint="Instale helm ou habilite dry-run para so visualizar.")
    if repo and repo_url:
        helm_repo_add(repo, repo_url, ctx)
        helm_repo_update(ctx)
        chart_ref = f"{repo}/{chart}"
    else:
        chart_ref = chart

    cmd = ["helm", "upgrade", "--install", release, chart_ref, "-n", namespace]
    if create_namespace:
        cmd.append("--create-namespace")
    for value in values or []:
        cmd.extend(["--set", value])
    if extra_args:
        cmd.extend(extra_args)
    run_cmd(cmd, ctx)


def kubectl_apply(target: str, ctx: ExecutionContext) -> None:
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    run_cmd(["kubectl", "apply", "-f", target], ctx)


def kubectl_create_ns(namespace: str, ctx: ExecutionContext) -> None:
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    run_cmd(["kubectl", "create", "namespace", namespace], ctx, check=False)
