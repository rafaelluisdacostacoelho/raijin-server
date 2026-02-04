"""Gerenciamento de VPN WireGuard - Pausar/Retomar para reduzir superfície de ataque.

Permite desabilitar temporariamente a VPN quando não estiver em uso,
reduzindo a superfície de ataque do servidor.

Comandos:
    raijin vpn-control status  - Mostra status atual
    raijin vpn-control pause   - Pausa a VPN (fecha portas)
    raijin vpn-control resume  - Retoma a VPN
    raijin vpn-control schedule - Configura horários automáticos
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from raijin_server.utils import ExecutionContext, require_root, run_cmd, write_file


WG_INTERFACE = "wg0"
WG_CONFIG = Path("/etc/wireguard/wg0.conf")
STATE_FILE = Path("/var/lib/raijin-server/vpn-state")
SCHEDULE_FILE = Path("/etc/cron.d/raijin-vpn-schedule")


def _get_wg_status() -> dict:
    """Obtém status atual do WireGuard."""
    status = {
        "installed": False,
        "config_exists": False,
        "interface_up": False,
        "peers_connected": 0,
        "last_handshake": None,
        "paused": False,
    }
    
    # Verifica se WireGuard está instalado
    result = subprocess.run(["which", "wg"], capture_output=True)
    status["installed"] = result.returncode == 0
    
    if not status["installed"]:
        return status
    
    # Verifica se config existe
    status["config_exists"] = WG_CONFIG.exists()
    
    # Verifica se interface está up
    result = subprocess.run(
        ["ip", "link", "show", WG_INTERFACE],
        capture_output=True, text=True
    )
    status["interface_up"] = result.returncode == 0 and "UP" in result.stdout
    
    # Conta peers conectados
    if status["interface_up"]:
        result = subprocess.run(
            ["wg", "show", WG_INTERFACE, "latest-handshakes"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    timestamp = int(parts[1])
                    if timestamp > 0:
                        status["peers_connected"] += 1
                        # Handshake nos últimos 3 minutos = conectado
                        if (datetime.now().timestamp() - timestamp) < 180:
                            status["last_handshake"] = datetime.fromtimestamp(timestamp)
    
    # Verifica estado de pausa
    if STATE_FILE.exists():
        state = STATE_FILE.read_text().strip()
        status["paused"] = state == "paused"
    
    return status


def _firewall_close_vpn(ctx: ExecutionContext) -> None:
    """Fecha porta da VPN no firewall."""
    import os
    vpn_port = os.environ.get("RAIJIN_VPN_PORT", "51820")
    
    typer.echo(f"Fechando porta UDP {vpn_port} no firewall...")
    run_cmd(["ufw", "delete", "allow", f"{vpn_port}/udp"], ctx, check=False)
    run_cmd(["ufw", "reload"], ctx, check=False)


def _firewall_open_vpn(ctx: ExecutionContext) -> None:
    """Abre porta da VPN no firewall."""
    import os
    vpn_port = os.environ.get("RAIJIN_VPN_PORT", "51820")
    
    typer.echo(f"Abrindo porta UDP {vpn_port} no firewall...")
    run_cmd(["ufw", "allow", f"{vpn_port}/udp", "comment", "WireGuard VPN"], ctx, check=False)
    run_cmd(["ufw", "reload"], ctx, check=False)


def status(ctx: ExecutionContext) -> None:
    """Mostra status atual da VPN."""
    status = _get_wg_status()
    
    typer.secho("\n🔐 Status da VPN WireGuard", fg=typer.colors.CYAN, bold=True)
    
    # Status geral
    if not status["installed"]:
        typer.secho("  ✗ WireGuard não instalado", fg=typer.colors.RED)
        return
    
    typer.secho("  ✓ WireGuard instalado", fg=typer.colors.GREEN)
    
    if not status["config_exists"]:
        typer.secho("  ✗ Configuração não encontrada", fg=typer.colors.YELLOW)
        typer.echo(f"    Esperado: {WG_CONFIG}")
        return
    
    typer.secho(f"  ✓ Configuração: {WG_CONFIG}", fg=typer.colors.GREEN)
    
    # Interface
    if status["paused"]:
        typer.secho("  ⏸ Interface: PAUSADA (porta fechada)", fg=typer.colors.YELLOW)
    elif status["interface_up"]:
        typer.secho(f"  ✓ Interface: {WG_INTERFACE} (UP)", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Interface: {WG_INTERFACE} (DOWN)", fg=typer.colors.RED)
    
    # Peers
    typer.echo(f"  👥 Peers conectados: {status['peers_connected']}")
    if status["last_handshake"]:
        typer.echo(f"  🤝 Último handshake: {status['last_handshake'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Detalhes WireGuard
    if status["interface_up"]:
        typer.secho("\n📊 Detalhes da Interface:", fg=typer.colors.CYAN)
        result = subprocess.run(
            ["wg", "show", WG_INTERFACE],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                typer.echo(f"  {line}")


def pause(ctx: ExecutionContext) -> None:
    """Pausa a VPN - fecha porta e desativa interface."""
    require_root(ctx)
    
    status = _get_wg_status()
    
    if status["paused"]:
        typer.secho("VPN já está pausada.", fg=typer.colors.YELLOW)
        return
    
    if not status["config_exists"]:
        typer.secho("VPN não configurada.", fg=typer.colors.RED)
        return
    
    typer.secho("\n⏸ Pausando VPN...", fg=typer.colors.CYAN, bold=True)
    
    # Avisar sobre peers conectados
    if status["peers_connected"] > 0:
        typer.secho(f"⚠️  {status['peers_connected']} peer(s) conectado(s) serão desconectados!", fg=typer.colors.YELLOW)
        if not typer.confirm("Continuar?", default=True):
            return
    
    # 1. Desativar interface
    typer.echo("Desativando interface WireGuard...")
    run_cmd(["wg-quick", "down", WG_INTERFACE], ctx, check=False)
    
    # 2. Fechar porta no firewall
    _firewall_close_vpn(ctx)
    
    # 3. Desabilitar serviço
    typer.echo("Desabilitando serviço WireGuard...")
    run_cmd(["systemctl", "disable", f"wg-quick@{WG_INTERFACE}"], ctx, check=False)
    
    # 4. Salvar estado
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ctx.dry_run:
        STATE_FILE.write_text("paused")
    
    typer.secho("\n✓ VPN pausada com sucesso!", fg=typer.colors.GREEN)
    typer.echo("  • Interface desativada")
    typer.echo("  • Porta fechada no firewall")
    typer.echo("  • Serviço desabilitado")
    typer.echo("\nPara retomar: raijin vpn-control resume")


def resume(ctx: ExecutionContext) -> None:
    """Retoma a VPN - abre porta e ativa interface."""
    require_root(ctx)
    
    status = _get_wg_status()
    
    if not status["paused"] and status["interface_up"]:
        typer.secho("VPN já está ativa.", fg=typer.colors.YELLOW)
        return
    
    if not status["config_exists"]:
        typer.secho("VPN não configurada.", fg=typer.colors.RED)
        return
    
    typer.secho("\n▶️ Retomando VPN...", fg=typer.colors.CYAN, bold=True)
    
    # 1. Abrir porta no firewall
    _firewall_open_vpn(ctx)
    
    # 2. Habilitar serviço
    typer.echo("Habilitando serviço WireGuard...")
    run_cmd(["systemctl", "enable", f"wg-quick@{WG_INTERFACE}"], ctx, check=False)
    
    # 3. Ativar interface
    typer.echo("Ativando interface WireGuard...")
    run_cmd(["wg-quick", "up", WG_INTERFACE], ctx, check=False)
    
    # 4. Atualizar estado
    if not ctx.dry_run and STATE_FILE.exists():
        STATE_FILE.write_text("active")
    
    typer.secho("\n✓ VPN retomada com sucesso!", fg=typer.colors.GREEN)
    typer.echo("  • Porta aberta no firewall")
    typer.echo("  • Serviço habilitado")
    typer.echo("  • Interface ativada")
    
    # Mostrar status
    status(ctx)


def schedule(ctx: ExecutionContext, enable: bool = True, start_hour: int = 8, end_hour: int = 22) -> None:
    """Configura horário automático para VPN.
    
    Por padrão, VPN ativa das 8h às 22h (horário de uso).
    Fora desse horário, VPN é pausada automaticamente.
    
    Args:
        enable: Habilitar ou desabilitar agendamento
        start_hour: Hora de início (VPN ativa)
        end_hour: Hora de fim (VPN pausa)
    """
    require_root(ctx)
    
    if not enable:
        typer.echo("Removendo agendamento...")
        if SCHEDULE_FILE.exists() and not ctx.dry_run:
            SCHEDULE_FILE.unlink()
        run_cmd(["systemctl", "restart", "cron"], ctx, check=False)
        typer.secho("✓ Agendamento removido.", fg=typer.colors.GREEN)
        return
    
    typer.secho(f"\n⏰ Configurando agendamento VPN", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  VPN ATIVA:  {start_hour:02d}:00 - {end_hour:02d}:00")
    typer.echo(f"  VPN PAUSADA: {end_hour:02d}:00 - {start_hour:02d}:00")
    
    cron_content = f"""# Raijin VPN Schedule - Gerado automaticamente
# VPN ativa das {start_hour}h às {end_hour}h
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Ativar VPN às {start_hour}h
0 {start_hour} * * * root /usr/local/bin/raijin vpn-control resume >> /var/log/raijin-vpn-schedule.log 2>&1

# Pausar VPN às {end_hour}h
0 {end_hour} * * * root /usr/local/bin/raijin vpn-control pause >> /var/log/raijin-vpn-schedule.log 2>&1
"""
    
    typer.echo(f"\nCriando {SCHEDULE_FILE}...")
    write_file(SCHEDULE_FILE, cron_content, ctx)
    
    if not ctx.dry_run:
        SCHEDULE_FILE.chmod(0o644)
    
    run_cmd(["systemctl", "restart", "cron"], ctx, check=False)
    
    typer.secho("\n✓ Agendamento configurado!", fg=typer.colors.GREEN)
    typer.echo(f"\nLogs em: /var/log/raijin-vpn-schedule.log")
    typer.echo("Para desativar: raijin vpn-control schedule --disable")


def run(ctx: ExecutionContext, action: str = "status") -> None:
    """Gerencia VPN WireGuard.
    
    Args:
        action: status|pause|resume|schedule
    """
    if action == "status":
        status(ctx)
    elif action == "pause":
        pause(ctx)
    elif action == "resume":
        resume(ctx)
    elif action == "schedule":
        schedule(ctx)
    else:
        typer.secho(f"Ação desconhecida: {action}", fg=typer.colors.RED)
        typer.echo("Ações válidas: status, pause, resume, schedule")
