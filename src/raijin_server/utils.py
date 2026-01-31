"""Utilitarios compartilhados para execucao dos modulos."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

import typer

# Configuracao de logging estruturado com rotacao para evitar inchar o disco
LOG_DIR = Path("/var/log/raijin-server")
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / "raijin-server.log"
except PermissionError:
    LOG_FILE = Path.home() / ".raijin-server.log"

MAX_LOG_BYTES = int(os.environ.get("RAIJIN_LOG_MAX_BYTES", 20 * 1024 * 1024))  # 20MB default
BACKUP_COUNT = int(os.environ.get("RAIJIN_LOG_BACKUP_COUNT", 5))

logger = logging.getLogger("raijin-server")
logger.setLevel(logging.INFO)


def _build_file_handler() -> RotatingFileHandler:
    """Cria handler com fallback para $HOME quando /var/log exige root."""
    try:
        return RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT)
    except PermissionError:
        fallback = Path.home() / ".raijin-server.log"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return RotatingFileHandler(fallback, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT)


file_handler = _build_file_handler()
stream_handler = logging.StreamHandler()


def active_log_file() -> Path:
    return Path(getattr(file_handler, "baseFilename", LOG_FILE))


def available_log_files() -> list[Path]:
    base = active_log_file()
    pattern = base.name + "*"
    return [p for p in sorted(base.parent.glob(pattern)) if p.is_file()]


def page_text(content: str) -> None:
    pager = shutil.which("less")
    if pager:
        subprocess.run([pager, "-R"], input=content, text=True, check=False)
    else:
        typer.echo(content)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logger.handlers.clear()
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
logger.propagate = False

PACKAGE_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_ROOT / "scripts"


@dataclass
class ExecutionContext:
    """Contexto de execucao compartilhado entre modulos."""

    dry_run: bool = False
    assume_yes: bool = True
    max_retries: int = 5
    retry_delay: int = 10
    retry_backoff: float = 1.5  # Multiplier for exponential backoff
    timeout: int = 600  # 10 min for slow connections
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # Controle interativo/diagnostico
    selected_steps: list[str] | None = None
    confirm_each_step: bool = False
    debug_snapshots: bool = False
    post_diagnose: bool = False
    color_prompts: bool = True
    interactive_steps: bool = False


def resolve_script_path(script_name: str) -> Path:
    """Retorna caminho absoluto para um script empacotado com o CLI."""

    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Script '{script_name}' nao encontrado em {SCRIPTS_DIR}")
    return script_path


def run_packaged_script(
    script_name: str,
    ctx: ExecutionContext,
    args: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Executa script shell embarcado usando bash para evitar problemas de permissoes."""

    script_path = resolve_script_path(script_name)
    cmd: list[str] = ["bash", str(script_path), *(args or [])]
    return run_cmd(cmd, ctx, env=env)


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
    retries: int | None = None,
) -> subprocess.CompletedProcess:
    """Executa comando exibindo (ou mascarando) a linha usada.

    Quando `dry_run` esta ativo, apenas mostra a linha sem executar.
    Suporta retry automatico para comandos que podem falhar temporariamente.
    """

    display = display_override or _format_cmd(cmd)
    prefix = "[dry-run] " if ctx.dry_run else ""
    if mask_output:
        logger.info("Executando comando com argumentos sensiveis (masked)")
        typer.echo(f"{prefix}[masked] comando executado (argumentos sensiveis ocultos)")
    else:
        logger.info(f"Executando: {display}")
        typer.echo(f"{prefix}$ {display}")

    if ctx.dry_run:
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    merged_env: MutableMapping[str, str] = os.environ.copy()
    if env:
        merged_env.update(env)

    max_attempts = retries if retries is not None else (ctx.max_retries if check else 1)
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                cmd,
                shell=use_shell,
                check=check,
                cwd=cwd,
                env=merged_env,
                timeout=ctx.timeout,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 or not check:
                return result
        except subprocess.TimeoutExpired as e:
            last_error = e
            msg = f"Comando timeout apos {ctx.timeout}s (tentativa {attempt}/{max_attempts})"
            logger.warning(msg)
            ctx.warnings.append(msg)
            if attempt < max_attempts:
                backoff_delay = int(ctx.retry_delay * (ctx.retry_backoff ** (attempt - 1)))
                typer.secho(
                    f"Timeout! Aguardando {backoff_delay}s antes de tentar novamente...",
                    fg=typer.colors.YELLOW,
                )
                time.sleep(backoff_delay)
        except subprocess.CalledProcessError as e:
            last_error = e
            msg = f"Comando falhou com codigo {e.returncode} (tentativa {attempt}/{max_attempts})"
            logger.error(f"{msg}: {e.stderr if hasattr(e, 'stderr') else ''}")
            if attempt < max_attempts:
                # Exponential backoff: delay * backoff^(attempt-1)
                backoff_delay = int(ctx.retry_delay * (ctx.retry_backoff ** (attempt - 1)))
                typer.secho(
                    f"Tentando novamente em {backoff_delay}s... (possivel instabilidade de rede)",
                    fg=typer.colors.YELLOW,
                )
                time.sleep(backoff_delay)
            else:
                ctx.errors.append(msg)
                if check:
                    raise
        except Exception as e:
            last_error = e
            msg = f"Erro inesperado: {type(e).__name__}: {e}"
            logger.error(msg)
            ctx.errors.append(msg)
            if check:
                raise

    if check and last_error:
        raise last_error

    return subprocess.CompletedProcess(args=cmd, returncode=1)


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


def _fix_broken_apt_sources(ctx: ExecutionContext) -> None:
    """Corrige repositórios APT quebrados (mirrors brasileiros problemáticos)."""
    if ctx.dry_run:
        typer.echo("[dry-run] Verificando/corrigindo repositórios APT...")
        return

    sources_list = Path("/etc/apt/sources.list")

    # Detecta se está usando mirror brasileiro quebrado
    needs_fix = False
    if sources_list.exists():
        content = sources_list.read_text()
        if "br.archive.ubuntu.com" in content or "br.ports.ubuntu.com" in content:
            needs_fix = True

    if not needs_fix:
        return

    typer.secho(
        "⚠ Detectado mirror brasileiro possivelmente quebrado. Corrigindo...",
        fg=typer.colors.YELLOW,
    )
    logger.warning("Corrigindo mirror brasileiro quebrado em sources.list")

    # Backup do original
    backup = sources_list.with_suffix(".list.bak")
    if not backup.exists():
        import shutil as sh
        sh.copy2(sources_list, backup)

    # Substitui mirror brasileiro pelo principal
    new_content = content.replace("br.archive.ubuntu.com", "archive.ubuntu.com")
    new_content = new_content.replace("br.ports.ubuntu.com", "ports.ubuntu.com")
    sources_list.write_text(new_content)

    typer.secho("✓ Repositórios corrigidos (backup em sources.list.bak)", fg=typer.colors.GREEN)


def apt_update(ctx: ExecutionContext) -> None:
    """Executa apt-get update, corrigindo repositórios quebrados se necessário."""
    _fix_broken_apt_sources(ctx)

    # Tenta o update; se falhar com erro de Release, tenta corrigir
    try:
        run_cmd(["apt-get", "update"], ctx, retries=2)
    except Exception as e:
        error_msg = str(e).lower()
        if "release" in error_msg or "no longer has" in error_msg:
            typer.secho(
                "⚠ Erro de repositório detectado. Tentando fallback...",
                fg=typer.colors.YELLOW,
            )
            # Força correção e tenta novamente
            ctx_temp = ExecutionContext(dry_run=False)
            _fix_broken_apt_sources(ctx_temp)
            run_cmd(["apt-get", "update"], ctx)
        else:
            raise


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


def _get_helm_release_status(release: str, namespace: str) -> str:
    """Retorna status do release Helm (lowercased) ou string vazia se nao existir."""
    try:
        import json
        result = subprocess.run(
            ["helm", "status", release, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            return ""
        data = json.loads(result.stdout)
        return str(data.get("info", {}).get("status", "")).lower()
    except Exception:
        return ""


def _get_helm_release_history(release: str, namespace: str) -> list:
    """Retorna histórico do release Helm."""
    try:
        import json
        result = subprocess.run(
            ["helm", "history", release, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []


def _diagnose_helm_release(release: str, namespace: str) -> None:
    """Mostra diagnóstico detalhado de um release Helm."""
    typer.secho(f"\n🔍 Diagnóstico do release '{release}':", fg=typer.colors.YELLOW)
    
    # Status atual
    status = _get_helm_release_status(release, namespace)
    typer.echo(f"  Status atual: {status or '(não encontrado)'}")
    
    # Histórico
    history = _get_helm_release_history(release, namespace)
    if history:
        typer.echo(f"  Histórico ({len(history)} revisões):")
        for rev in history[-5:]:  # Últimas 5 revisões
            typer.echo(f"    Rev {rev.get('revision')}: {rev.get('status')} - {rev.get('description', '')[:50]}")
    
    # Secrets do Helm (onde guarda estado)
    try:
        result = subprocess.run(
            ["kubectl", "get", "secrets", "-n", namespace, "-l", f"name={release},owner=helm", "-o", "name"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout.strip():
            secrets = result.stdout.strip().split("\n")
            typer.echo(f"  Secrets do Helm: {len(secrets)}")
            for s in secrets[-5:]:
                typer.echo(f"    {s}")
    except Exception:
        pass
    
    # Pods relacionados
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "wide", "--no-headers"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout.strip():
            typer.echo("  Pods:")
            for line in result.stdout.strip().split("\n")[:5]:
                typer.echo(f"    {line}")
    except Exception:
        pass


def _force_cleanup_helm_release(release: str, namespace: str) -> bool:
    """Limpeza forçada de release Helm travado - remove secrets diretamente."""
    typer.secho(f"  Limpeza forçada do release '{release}'...", fg=typer.colors.YELLOW)
    logger.warning(f"Executando limpeza forçada do release {release} em {namespace}")
    
    try:
        # 1. Primeiro tenta uninstall normal com --no-hooks (pula hooks que podem estar travando)
        result = subprocess.run(
            ["helm", "uninstall", release, "-n", namespace, "--no-hooks", "--wait", "--timeout", "2m"],
            capture_output=True,
            text=True,
            timeout=150,
        )
        
        if result.returncode == 0:
            typer.secho(f"  ✓ Release removido via helm uninstall", fg=typer.colors.GREEN)
            time.sleep(3)
            return True
        
        # 2. Se falhou, remove os secrets do Helm diretamente
        typer.echo("  Helm uninstall falhou, removendo secrets diretamente...")
        logger.warning("Removendo secrets do Helm diretamente")
        
        # Lista secrets do Helm para este release
        result = subprocess.run(
            ["kubectl", "get", "secrets", "-n", namespace, "-l", f"name={release},owner=helm", "-o", "name"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        if result.stdout.strip():
            secrets = result.stdout.strip().split("\n")
            for secret in secrets:
                secret_name = secret.replace("secret/", "")
                subprocess.run(
                    ["kubectl", "delete", "secret", secret_name, "-n", namespace],
                    capture_output=True,
                    timeout=30,
                )
                typer.echo(f"    Removido: {secret_name}")
            
            time.sleep(3)
            typer.secho(f"  ✓ Secrets do Helm removidos", fg=typer.colors.GREEN)
            return True
        else:
            typer.echo("  Nenhum secret do Helm encontrado")
            return True
            
    except Exception as e:
        logger.error(f"Erro na limpeza forçada: {e}")
        typer.secho(f"  ✗ Erro na limpeza: {e}", fg=typer.colors.RED)
        return False


def _cleanup_pending_helm_release(release: str, namespace: str, ctx: ExecutionContext) -> None:
    """Remove release Helm em estado pendente que bloqueia novas operacoes."""
    if ctx.dry_run:
        return

    status = _get_helm_release_status(release, namespace)
    if not status:
        return

    # Estados que bloqueiam: pending-install, pending-upgrade, pending-rollback
    if not status.startswith("pending"):
        return
    
    typer.secho(
        f"\n⚠ Release '{release}' em estado '{status}' - bloqueando novas operações",
        fg=typer.colors.YELLOW,
    )
    
    # Mostra diagnóstico
    _diagnose_helm_release(release, namespace)
    
    typer.echo("\n  Tentando recuperar...")
    
    # 1. Tenta rollback primeiro (funciona para pending-upgrade)
    if status == "pending-upgrade":
        typer.echo("  Tentando rollback para versão anterior...")
        result = subprocess.run(
            ["helm", "rollback", release, "-n", namespace, "--wait", "--timeout", "2m"],
            capture_output=True,
            text=True,
            timeout=150,
        )
        
        if result.returncode == 0:
            new_status = _get_helm_release_status(release, namespace)
            if not new_status.startswith("pending"):
                typer.secho(f"  ✓ Rollback bem-sucedido (status: {new_status})", fg=typer.colors.GREEN)
                return
        
        typer.echo("  Rollback não resolveu...")
    
    # 2. Tenta uninstall normal
    typer.echo("  Tentando helm uninstall...")
    result = subprocess.run(
        ["helm", "uninstall", release, "-n", namespace, "--wait", "--timeout", "3m"],
        capture_output=True,
        text=True,
        timeout=200,
    )
    
    if result.returncode == 0:
        typer.secho(f"  ✓ Release removido com sucesso", fg=typer.colors.GREEN)
        time.sleep(3)
        return
    
    # 3. Se ainda falhou, força limpeza
    typer.echo("  Uninstall normal falhou, tentando limpeza forçada...")
    _force_cleanup_helm_release(release, namespace)
    
    # Verifica resultado final
    final_status = _get_helm_release_status(release, namespace)
    if final_status:
        typer.secho(f"  ⚠ Release ainda existe com status: {final_status}", fg=typer.colors.YELLOW)
    else:
        typer.secho(f"  ✓ Release '{release}' limpo com sucesso", fg=typer.colors.GREEN)


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
    """Executa helm upgrade --install com opcoes comuns.
    
    Automaticamente detecta e limpa releases em estado pendente antes de instalar.
    """

    ensure_tool("helm", ctx, install_hint="Instale helm ou habilite dry-run para so visualizar.")
    
    # Limpa releases pendentes antes de tentar instalar
    _cleanup_pending_helm_release(release, namespace, ctx)
    
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
    
    try:
        run_cmd(cmd, ctx)
    except Exception as e:
        err_text = str(e).lower()
        # Se falhou por operacao em progresso, tenta limpar e reinstalar uma vez
        if "another operation" in err_text and "in progress" in err_text:
            typer.secho(
                f"⚠ Helm detectou operacao pendente em '{release}'. Limpando e tentando novamente...",
                fg=typer.colors.YELLOW,
            )
            _cleanup_pending_helm_release(release, namespace, ctx)
            run_cmd(cmd, ctx)
        else:
            raise


def kubectl_apply(target: str, ctx: ExecutionContext) -> None:
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    run_cmd(["kubectl", "apply", "-f", target], ctx)


def kubectl_create_ns(namespace: str, ctx: ExecutionContext) -> None:
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl ou habilite dry-run.")
    run_cmd(["kubectl", "create", "namespace", namespace], ctx, check=False)
