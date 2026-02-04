"""Gerenciamento de SSH - Habilitar/Desabilitar para reduzir superfície de ataque.

Permite desabilitar temporariamente o SSH quando não estiver em uso,
reduzindo a superfície de ataque do servidor.

IMPORTANTE: Use com cuidado! Se desabilitar SSH sem outra forma de acesso
(console físico, VPN, etc.), você pode perder acesso ao servidor.

Comandos:
    raijin ssh-control status  - Mostra status atual
    raijin ssh-control disable - Desabilita SSH
    raijin ssh-control enable  - Habilita SSH
    raijin ssh-control schedule - Configura horários automáticos
    raijin ssh-control port    - Muda porta SSH
"""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, require_root, run_cmd, write_file


SSHD_CONFIG = Path("/etc/ssh/sshd_config")
SSHD_CONFIG_BACKUP = Path("/etc/ssh/sshd_config.raijin.bak")
STATE_FILE = Path("/var/lib/raijin-server/ssh-state")
SCHEDULE_FILE = Path("/etc/cron.d/raijin-ssh-schedule")


def _get_ssh_port() -> int:
    """Obtém porta atual do SSH."""
    port = os.environ.get("RAIJIN_SSH_PORT", "22")
    
    # Se não está em env, tenta ler do config
    if port == "22" and SSHD_CONFIG.exists():
        content = SSHD_CONFIG.read_text()
        match = re.search(r'^Port\s+(\d+)', content, re.MULTILINE)
        if match:
            port = match.group(1)
    
    return int(port)


def _get_ssh_status() -> dict:
    """Obtém status atual do SSH."""
    status = {
        "installed": False,
        "running": False,
        "enabled": False,
        "port": 22,
        "port_open": False,
        "active_sessions": 0,
        "password_auth": True,
        "root_login": False,
        "allowed_users": [],
        "disabled_by_raijin": False,
    }
    
    # Verifica se SSH está instalado
    result = subprocess.run(["which", "sshd"], capture_output=True)
    status["installed"] = result.returncode == 0
    
    if not status["installed"]:
        return status
    
    # Porta atual
    status["port"] = _get_ssh_port()
    
    # Verifica se serviço está rodando
    result = subprocess.run(
        ["systemctl", "is-active", "ssh"],
        capture_output=True, text=True
    )
    status["running"] = result.stdout.strip() == "active"
    
    # Verifica se está habilitado no boot
    result = subprocess.run(
        ["systemctl", "is-enabled", "ssh"],
        capture_output=True, text=True
    )
    status["enabled"] = result.stdout.strip() == "enabled"
    
    # Verifica porta no firewall
    result = subprocess.run(
        ["ufw", "status", "verbose"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        status["port_open"] = str(status["port"]) in result.stdout
    
    # Conta sessões ativas
    result = subprocess.run(
        ["who"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        status["active_sessions"] = len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
    
    # Configurações do sshd_config
    if SSHD_CONFIG.exists():
        content = SSHD_CONFIG.read_text()
        
        # Password auth
        match = re.search(r'^PasswordAuthentication\s+(yes|no)', content, re.MULTILINE | re.IGNORECASE)
        if match:
            status["password_auth"] = match.group(1).lower() == "yes"
        
        # Root login
        match = re.search(r'^PermitRootLogin\s+(\S+)', content, re.MULTILINE | re.IGNORECASE)
        if match:
            status["root_login"] = match.group(1).lower() in ["yes", "prohibit-password", "without-password"]
        
        # Allowed users
        match = re.search(r'^AllowUsers\s+(.+)', content, re.MULTILINE)
        if match:
            status["allowed_users"] = match.group(1).split()
    
    # Estado Raijin
    if STATE_FILE.exists():
        state = STATE_FILE.read_text().strip()
        status["disabled_by_raijin"] = state == "disabled"
    
    return status


def _firewall_close_ssh(ctx: ExecutionContext, port: int) -> None:
    """Fecha porta SSH no firewall."""
    typer.echo(f"Fechando porta TCP {port} no firewall...")
    run_cmd(["ufw", "delete", "allow", f"{port}/tcp"], ctx, check=False)
    run_cmd(["ufw", "reload"], ctx, check=False)


def _firewall_open_ssh(ctx: ExecutionContext, port: int) -> None:
    """Abre porta SSH no firewall."""
    typer.echo(f"Abrindo porta TCP {port} no firewall...")
    run_cmd(["ufw", "allow", f"{port}/tcp", "comment", "SSH Remote Access"], ctx, check=False)
    run_cmd(["ufw", "reload"], ctx, check=False)


def status(ctx: ExecutionContext) -> None:
    """Mostra status atual do SSH."""
    ssh_status = _get_ssh_status()
    
    typer.secho("\n🔓 Status do SSH", fg=typer.colors.CYAN, bold=True)
    
    # Status geral
    if not ssh_status["installed"]:
        typer.secho("  ✗ SSH não instalado", fg=typer.colors.RED)
        return
    
    typer.secho("  ✓ SSH instalado", fg=typer.colors.GREEN)
    
    # Serviço
    if ssh_status["disabled_by_raijin"]:
        typer.secho("  ⏸ Serviço: DESABILITADO (por Raijin)", fg=typer.colors.YELLOW)
    elif ssh_status["running"]:
        typer.secho(f"  ✓ Serviço: ATIVO (porta {ssh_status['port']})", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Serviço: PARADO", fg=typer.colors.RED)
    
    # Boot
    if ssh_status["enabled"]:
        typer.secho("  ✓ Inicia no boot: SIM", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Inicia no boot: NÃO", fg=typer.colors.YELLOW)
    
    # Firewall
    if ssh_status["port_open"]:
        typer.secho(f"  ✓ Firewall: porta {ssh_status['port']} ABERTA", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Firewall: porta {ssh_status['port']} FECHADA", fg=typer.colors.YELLOW)
    
    # Sessões
    typer.echo(f"  👥 Sessões ativas: {ssh_status['active_sessions']}")
    
    # Configurações de segurança
    typer.secho("\n🔒 Configurações de Segurança:", fg=typer.colors.CYAN)
    
    if ssh_status["password_auth"]:
        typer.secho("  ⚠️  Autenticação por senha: HABILITADA", fg=typer.colors.YELLOW)
        typer.echo("      Recomendado: desabilitar e usar apenas chaves SSH")
    else:
        typer.secho("  ✓ Autenticação por senha: DESABILITADA", fg=typer.colors.GREEN)
    
    if ssh_status["root_login"]:
        typer.secho("  ⚠️  Login como root: PERMITIDO", fg=typer.colors.YELLOW)
        typer.echo("      Recomendado: desabilitar login root via SSH")
    else:
        typer.secho("  ✓ Login como root: BLOQUEADO", fg=typer.colors.GREEN)
    
    if ssh_status["allowed_users"]:
        typer.secho(f"  ✓ Usuários permitidos: {', '.join(ssh_status['allowed_users'])}", fg=typer.colors.GREEN)
    else:
        typer.secho("  ⚠️  Todos usuários podem fazer login", fg=typer.colors.YELLOW)


def disable(ctx: ExecutionContext, force: bool = False) -> None:
    """Desabilita SSH - para serviço e fecha porta."""
    require_root(ctx)
    
    ssh_status = _get_ssh_status()
    
    if ssh_status["disabled_by_raijin"]:
        typer.secho("SSH já está desabilitado.", fg=typer.colors.YELLOW)
        return
    
    if not ssh_status["installed"]:
        typer.secho("SSH não instalado.", fg=typer.colors.RED)
        return
    
    typer.secho("\n⏸ Desabilitando SSH...", fg=typer.colors.CYAN, bold=True)
    typer.secho("⚠️  ATENÇÃO: Você perderá acesso remoto SSH!", fg=typer.colors.YELLOW, bold=True)
    
    # Verifica se tem outras formas de acesso
    typer.echo("\nCertifique-se de ter outra forma de acesso:")
    typer.echo("  • Console físico/IPMI/iLO")
    typer.echo("  • VPN ativa (raijin vpn-control status)")
    typer.echo("  • Acesso serial")
    
    # Avisar sobre sessões ativas
    if ssh_status["active_sessions"] > 0:
        typer.secho(f"\n⚠️  {ssh_status['active_sessions']} sessão(ões) ativa(s)!", fg=typer.colors.YELLOW)
        
    if not force:
        if not typer.confirm("\nTem certeza que deseja continuar?", default=False):
            typer.echo("Operação cancelada.")
            return
    
    # 1. Parar serviço
    typer.echo("Parando serviço SSH...")
    run_cmd(["systemctl", "stop", "ssh"], ctx, check=False)
    
    # 2. Desabilitar no boot
    typer.echo("Desabilitando SSH no boot...")
    run_cmd(["systemctl", "disable", "ssh"], ctx, check=False)
    
    # 3. Fechar porta no firewall
    _firewall_close_ssh(ctx, ssh_status["port"])
    
    # 4. Salvar estado
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ctx.dry_run:
        STATE_FILE.write_text("disabled")
    
    typer.secho("\n✓ SSH desabilitado com sucesso!", fg=typer.colors.GREEN)
    typer.echo("  • Serviço parado")
    typer.echo("  • Porta fechada no firewall")
    typer.echo("  • Desabilitado no boot")
    typer.echo("\nPara reabilitar: raijin ssh-control enable")


def enable(ctx: ExecutionContext) -> None:
    """Habilita SSH - inicia serviço e abre porta."""
    require_root(ctx)
    
    ssh_status = _get_ssh_status()
    
    if not ssh_status["disabled_by_raijin"] and ssh_status["running"]:
        typer.secho("SSH já está ativo.", fg=typer.colors.YELLOW)
        return
    
    if not ssh_status["installed"]:
        typer.secho("SSH não instalado.", fg=typer.colors.RED)
        return
    
    typer.secho("\n▶️ Habilitando SSH...", fg=typer.colors.CYAN, bold=True)
    
    # 1. Habilitar no boot
    typer.echo("Habilitando SSH no boot...")
    run_cmd(["systemctl", "enable", "ssh"], ctx, check=False)
    
    # 2. Iniciar serviço
    typer.echo("Iniciando serviço SSH...")
    run_cmd(["systemctl", "start", "ssh"], ctx, check=False)
    
    # 3. Abrir porta no firewall
    _firewall_open_ssh(ctx, ssh_status["port"])
    
    # 4. Atualizar estado
    if not ctx.dry_run and STATE_FILE.exists():
        STATE_FILE.write_text("enabled")
    
    typer.secho("\n✓ SSH habilitado com sucesso!", fg=typer.colors.GREEN)
    typer.echo("  • Serviço iniciado")
    typer.echo("  • Porta aberta no firewall")
    typer.echo("  • Habilitado no boot")
    
    # Mostrar status
    status(ctx)


def change_port(ctx: ExecutionContext, new_port: int) -> None:
    """Muda a porta do SSH.
    
    Args:
        new_port: Nova porta (recomendado: acima de 1024)
    """
    require_root(ctx)
    
    ssh_status = _get_ssh_status()
    old_port = ssh_status["port"]
    
    if new_port == old_port:
        typer.secho(f"SSH já está na porta {new_port}.", fg=typer.colors.YELLOW)
        return
    
    if new_port < 1 or new_port > 65535:
        typer.secho("Porta inválida. Use entre 1-65535.", fg=typer.colors.RED)
        return
    
    typer.secho(f"\n🔄 Mudando porta SSH: {old_port} → {new_port}", fg=typer.colors.CYAN, bold=True)
    
    if new_port < 1024:
        typer.secho("⚠️  Portas abaixo de 1024 são bem conhecidas e mais fáceis de escanear.", fg=typer.colors.YELLOW)
    
    if not SSHD_CONFIG.exists():
        typer.secho(f"Arquivo {SSHD_CONFIG} não encontrado.", fg=typer.colors.RED)
        return
    
    # Backup do config
    typer.echo(f"Criando backup: {SSHD_CONFIG_BACKUP}")
    if not ctx.dry_run:
        import shutil
        shutil.copy(SSHD_CONFIG, SSHD_CONFIG_BACKUP)
    
    # Lê e modifica config
    content = SSHD_CONFIG.read_text()
    
    # Substitui ou adiciona Port
    if re.search(r'^#?\s*Port\s+\d+', content, re.MULTILINE):
        content = re.sub(r'^#?\s*Port\s+\d+', f'Port {new_port}', content, flags=re.MULTILINE)
    else:
        content = f"Port {new_port}\n{content}"
    
    typer.echo(f"Atualizando {SSHD_CONFIG}...")
    write_file(SSHD_CONFIG, content, ctx)
    
    # Atualiza firewall
    typer.echo("Atualizando firewall...")
    _firewall_close_ssh(ctx, old_port)
    _firewall_open_ssh(ctx, new_port)
    
    # Restart SSH
    typer.echo("Reiniciando SSH...")
    run_cmd(["systemctl", "restart", "ssh"], ctx, check=False)
    
    typer.secho(f"\n✓ Porta SSH alterada para {new_port}!", fg=typer.colors.GREEN)
    typer.echo(f"\n📝 Atualize seus clientes SSH para usar a nova porta:")
    typer.echo(f"   ssh -p {new_port} user@servidor")
    typer.echo(f"\n   Ou em ~/.ssh/config:")
    typer.echo(f"   Host meuservidor")
    typer.echo(f"     Port {new_port}")


def schedule(ctx: ExecutionContext, enable_schedule: bool = True, start_hour: int = 8, end_hour: int = 22) -> None:
    """Configura horário automático para SSH.
    
    Por padrão, SSH ativo das 8h às 22h (horário de trabalho).
    Fora desse horário, SSH é desabilitado automaticamente.
    
    Args:
        enable_schedule: Habilitar ou desabilitar agendamento
        start_hour: Hora de início (SSH ativo)
        end_hour: Hora de fim (SSH desabilita)
    """
    require_root(ctx)
    
    if not enable_schedule:
        typer.echo("Removendo agendamento...")
        if SCHEDULE_FILE.exists() and not ctx.dry_run:
            SCHEDULE_FILE.unlink()
        run_cmd(["systemctl", "restart", "cron"], ctx, check=False)
        typer.secho("✓ Agendamento removido.", fg=typer.colors.GREEN)
        return
    
    typer.secho(f"\n⏰ Configurando agendamento SSH", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  SSH ATIVO:     {start_hour:02d}:00 - {end_hour:02d}:00")
    typer.echo(f"  SSH DESATIVADO: {end_hour:02d}:00 - {start_hour:02d}:00")
    
    typer.secho("\n⚠️  ATENÇÃO: Fora do horário configurado, você NÃO terá acesso SSH!", fg=typer.colors.YELLOW, bold=True)
    typer.echo("Certifique-se de ter outra forma de acesso (console, VPN, etc.)")
    
    if not typer.confirm("\nConfirmar agendamento?", default=False):
        typer.echo("Operação cancelada.")
        return
    
    cron_content = f"""# Raijin SSH Schedule - Gerado automaticamente
# SSH ativo das {start_hour}h às {end_hour}h
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Ativar SSH às {start_hour}h
0 {start_hour} * * * root /usr/local/bin/raijin ssh-control enable >> /var/log/raijin-ssh-schedule.log 2>&1

# Desativar SSH às {end_hour}h
0 {end_hour} * * * root /usr/local/bin/raijin ssh-control disable --force >> /var/log/raijin-ssh-schedule.log 2>&1
"""
    
    typer.echo(f"\nCriando {SCHEDULE_FILE}...")
    write_file(SCHEDULE_FILE, cron_content, ctx)
    
    if not ctx.dry_run:
        SCHEDULE_FILE.chmod(0o644)
    
    run_cmd(["systemctl", "restart", "cron"], ctx, check=False)
    
    typer.secho("\n✓ Agendamento configurado!", fg=typer.colors.GREEN)
    typer.echo(f"\nLogs em: /var/log/raijin-ssh-schedule.log")
    typer.echo("Para desativar: raijin ssh-control schedule --disable")


def run(ctx: ExecutionContext, action: str = "status", port: int = None) -> None:
    """Gerencia serviço SSH.
    
    Args:
        action: status|enable|disable|schedule|port
        port: Nova porta (apenas para action=port)
    """
    if action == "status":
        status(ctx)
    elif action == "enable":
        enable(ctx)
    elif action == "disable":
        disable(ctx)
    elif action == "schedule":
        schedule(ctx)
    elif action == "port":
        if port is None:
            typer.secho("Especifique a nova porta: --port NUMERO", fg=typer.colors.RED)
            return
        change_port(ctx, port)
    else:
        typer.secho(f"Ação desconhecida: {action}", fg=typer.colors.RED)
        typer.echo("Ações válidas: status, enable, disable, schedule, port")
