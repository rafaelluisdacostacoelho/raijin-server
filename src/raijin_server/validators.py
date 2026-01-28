"""Validadores de pre-requisitos do sistema."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import List, Tuple

import typer

from raijin_server.utils import ExecutionContext, logger


class ValidationError(Exception):
    """Erro de validacao de pre-requisitos."""

    pass


def check_os_version() -> Tuple[bool, str]:
    """Valida se o OS e Ubuntu Server 24.04 ou compativel."""
    try:
        if platform.system() != "Linux":
            return False, f"Sistema operacional nao suportado: {platform.system()}"

        # Verifica /etc/os-release
        os_release = Path("/etc/os-release")
        if not os_release.exists():
            return False, "Arquivo /etc/os-release nao encontrado"

        content = os_release.read_text()
        is_ubuntu = "ubuntu" in content.lower()

        if not is_ubuntu:
            return False, "Sistema nao e Ubuntu"

        # Extrai versao
        version_line = [line for line in content.split("\n") if line.startswith("VERSION_ID=")]
        if version_line:
            version = version_line[0].split("=")[1].strip('"')
            version_major = float(version.split(".")[0])
            if version_major < 20:
                return False, f"Ubuntu {version} muito antigo (minimo: 20.04)"

        return True, f"Ubuntu detectado: {version if version_line else 'versao desconhecida'}"
    except Exception as e:
        return False, f"Erro ao verificar OS: {e}"


def check_disk_space(min_gb: int = 20) -> Tuple[bool, str]:
    """Verifica espaco em disco disponivel."""
    try:
        stat = os.statvfs("/")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        if free_gb < min_gb:
            return False, f"Espaco insuficiente: {free_gb:.1f}GB (minimo: {min_gb}GB)"
        return True, f"Espaco em disco OK: {free_gb:.1f}GB disponiveis"
    except Exception as e:
        return False, f"Erro ao verificar disco: {e}"


def check_memory(min_gb: int = 4) -> Tuple[bool, str]:
    """Verifica memoria RAM disponivel."""
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        mem_total_kb = int([line for line in meminfo.split("\n") if "MemTotal" in line][0].split()[1])
        mem_total_gb = mem_total_kb / (1024**2)
        if mem_total_gb < min_gb:
            return False, f"Memoria insuficiente: {mem_total_gb:.1f}GB (minimo: {min_gb}GB)"
        return True, f"Memoria RAM OK: {mem_total_gb:.1f}GB"
    except Exception as e:
        return False, f"Erro ao verificar memoria: {e}"


def check_connectivity(hosts: List[str] | None = None) -> Tuple[bool, str]:
    """Verifica conectividade com internet via ICMP e HTTP."""
    if hosts is None:
        hosts = ["8.8.8.8", "1.1.1.1"]

    # Primeiro tenta ICMP
    for host in hosts:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True, f"Conectividade OK (testado: {host})"
        except Exception:
            continue

    # Fallback HTTP (caso ICMP seja bloqueado)
    try:
        req = urllib.request.Request("https://www.google.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5):
            return True, "Conectividade HTTP OK (https://www.google.com)"
    except Exception:
        return False, "Sem conectividade com internet (ICMP e HTTP falharam)"


def check_required_commands(commands: List[str] | None = None) -> Tuple[bool, List[str]]:
    """Verifica se comandos essenciais estao disponiveis."""
    if commands is None:
        commands = ["curl", "wget", "apt-get", "systemctl"]

    missing = []
    for cmd in commands:
        if not shutil.which(cmd):
            missing.append(cmd)

    if missing:
        return False, missing
    return True, []


def check_virtualenv() -> Tuple[bool, str]:
    """Valida se a execucao esta dentro de um ambiente isolado (venv/pyenv)."""

    in_venv = sys.prefix != sys.base_prefix or os.environ.get("VIRTUAL_ENV")
    externally_managed = Path(sys.prefix).joinpath("../EXTERNALLY-MANAGED").resolve()

    if in_venv:
        return True, "Executando em ambiente virtual"

    if externally_managed.exists():
        return False, (
            "Python gerenciado pelo sistema. Crie um venv: "
            "python3 -m venv .venv && source .venv/bin/activate && pip install -U pip setuptools && "
            "pip install raijin-server"
        )

    return False, (
        "Execucao fora de venv detectada. Crie um venv: "
        "python3 -m venv .venv && source .venv/bin/activate && pip install -U pip setuptools && "
        "pip install raijin-server"
    )


def check_is_root() -> Tuple[bool, str]:
    """Verifica se esta executando como root."""
    if os.geteuid() == 0:
        return True, "Executando como root"
    return False, "Usuario nao e root (reexecute com: sudo -E raijin-server ...)"


def validate_system_requirements(ctx: ExecutionContext, skip_root: bool = False) -> bool:
    """Executa todas as validacoes de pre-requisitos.

    Returns:
        True se todas as validacoes passaram, False caso contrario.
    """
    logger.info("Iniciando validacao de pre-requisitos do sistema...")
    typer.secho("\n=== Validacao de Pre-requisitos ===", fg=typer.colors.CYAN, bold=True)

    checks = [
        ("Ambiente Python", check_virtualenv()),
        ("Sistema Operacional", check_os_version()),
        ("Espaco em Disco", check_disk_space()),
        ("Memoria RAM", check_memory()),
        ("Conectividade", check_connectivity()),
    ]

    if not skip_root:
        checks.insert(0, ("Permissoes Root", check_is_root()))

    # Comandos essenciais
    cmd_ok, missing = check_required_commands()
    if cmd_ok:
        checks.append(("Comandos Essenciais", (True, "Todos os comandos disponiveis")))
    else:
        install_hint = "sudo apt-get update && sudo apt-get install -y " + " ".join(missing)
        checks.append(("Comandos Essenciais", (False, f"Faltando: {', '.join(missing)} | Sugestao: {install_hint}")))

    all_passed = True
    for name, (passed, message) in checks:
        icon = "✓" if passed else "✗"
        color = typer.colors.GREEN if passed else typer.colors.RED
        typer.secho(f"  {icon} {name}: {message}", fg=color)
        logger.info(f"Validacao '{name}': {'PASS' if passed else 'FAIL'} - {message}")

        if not passed:
            all_passed = False
            ctx.errors.append(f"Validacao falhou: {name} - {message}")

    typer.echo("")

    if not all_passed:
        if ctx.dry_run:
            typer.secho("⚠ Validacoes falharam, mas continuando em modo dry-run", fg=typer.colors.YELLOW)
            return True
        else:
            typer.secho("✗ Pre-requisitos nao atendidos. Corrija os problemas acima.", fg=typer.colors.RED, bold=True)
            logger.error("Pre-requisitos do sistema nao atendidos")
            return False

    typer.secho("✓ Todos os pre-requisitos atendidos!", fg=typer.colors.GREEN, bold=True)
    logger.info("Validacao de pre-requisitos concluida com sucesso")
    return True


def check_module_dependencies(module: str, ctx: ExecutionContext) -> bool:
    """Verifica se os modulos dependentes ja foram executados.

    Args:
        module: Nome do modulo a ser executado
        ctx: Contexto de execucao

    Returns:
        True se todas as dependencias foram satisfeitas
    """
    dependencies = {
        "kubernetes": ["essentials", "network", "firewall"],
        "calico": ["kubernetes"],
        "cert_manager": ["kubernetes", "traefik"],
        "istio": ["kubernetes", "calico"],
        "traefik": ["kubernetes"],
        "kong": ["kubernetes"],
        "minio": ["kubernetes"],
        "prometheus": ["kubernetes"],
        "grafana": ["kubernetes", "prometheus"],
        "loki": ["kubernetes"],
        "secrets": ["kubernetes"],
        "harness": ["kubernetes"],
        "velero": ["kubernetes"],
        "kafka": ["kubernetes"],
        "observability_ingress": ["traefik", "prometheus", "grafana"],
        "observability_dashboards": ["prometheus", "grafana"],
        "apokolips_demo": ["kubernetes", "traefik"],
    }

    if module not in dependencies:
        return True

    required = dependencies[module]
    missing = []

    # Verifica arquivos de estado
    state_dir = Path(os.environ.get("RAIJIN_STATE_DIR", "/var/lib/raijin-server/state"))
    if not state_dir.exists():
        state_dir = Path.home() / ".local/share/raijin-server/state"

    for dep in required:
        state_file = state_dir / f"{dep}.done"
        if not state_file.exists():
            missing.append(dep)

    if missing:
        if ctx.dry_run:
            typer.secho(
                f"⚠ Modulo '{module}' requer: {', '.join(missing)} (ignorado em dry-run)",
                fg=typer.colors.YELLOW,
            )
            return True
        else:
            typer.secho(
                f"✗ Modulo '{module}' requer os seguintes modulos executados primeiro: {', '.join(missing)}",
                fg=typer.colors.RED,
            )
            logger.error(f"Dependencias nao satisfeitas para modulo '{module}': {missing}")
            return False

    return True
