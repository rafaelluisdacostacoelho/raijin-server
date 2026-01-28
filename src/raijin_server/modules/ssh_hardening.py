"""Hardening de SSH com usuario dedicado e chaves publicas."""

from __future__ import annotations

import os
import pwd
from pathlib import Path

import typer

from raijin_server.utils import ExecutionContext, apt_install, require_root, run_cmd, write_file

SSHD_DROPIN = Path("/etc/ssh/sshd_config.d/99-raijin.conf")
FAIL2BAN_JAIL = Path("/etc/fail2ban/jail.d/raijin-sshd.conf")
AUTHORIZED_KEYS_TEMPLATE = "# gerenciado pelo raijin-server\n{key}\n"


def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def _ensure_user(username: str, ctx: ExecutionContext) -> None:
    if _user_exists(username):
        typer.echo(f"Usuario {username} ja existe, reutilizando...")
        return

    typer.echo(f"Criando usuario {username} sem senha...")
    run_cmd(["useradd", "-m", "-s", "/bin/bash", username], ctx)
    run_cmd(["passwd", "-l", username], ctx, check=False)


def _write_authorized_keys(username: str, content: str, ctx: ExecutionContext) -> None:
    ssh_dir = Path("/home") / username / ".ssh"
    auth_file = ssh_dir / "authorized_keys"

    if ctx.dry_run:
        typer.echo(f"[dry-run] escrever {auth_file} com chave publica")
        return

    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    auth_file.write_text(AUTHORIZED_KEYS_TEMPLATE.format(key=content.strip()))
    os.chmod(auth_file, 0o600)
    run_cmd(["chown", "-R", f"{username}:{username}", str(ssh_dir)], ctx)


def _load_public_key(path_input: str) -> str:
    path = Path(path_input).expanduser()
    if path.exists():
        return path.read_text().strip()
    typer.echo("Arquivo nao encontrado. Cole a chave publica completa (ssh-ed25519...).")
    key = typer.prompt("Chave publica", default="")
    if not key:
        raise typer.BadParameter("Nenhuma chave publica fornecida.")
    return key.strip()


def run(ctx: ExecutionContext) -> None:
    """Configura SSH seguro com usuario dedicado e chaves publicas."""
    require_root(ctx)

    typer.echo("Hardening de SSH em andamento...")
    apt_install(["openssh-server", "fail2ban"], ctx)

    username = typer.prompt("Usuario administrativo para SSH", default="adminops")
    ssh_port = typer.prompt("Porta SSH", default="22")
    sudo_access = typer.confirm("Adicionar usuario ao grupo sudo?", default=True)
    pubkey_path = typer.prompt(
        "Arquivo com chave publica (ENTER para ~/.ssh/id_ed25519.pub)",
        default=str(Path.home() / ".ssh/id_ed25519.pub"),
    )

    public_key = _load_public_key(pubkey_path)

    _ensure_user(username, ctx)
    if sudo_access:
        run_cmd(["usermod", "-aG", "sudo", username], ctx)

    _write_authorized_keys(username, public_key, ctx)

    config = f"""
# Arquivo gerenciado pelo raijin-server
Port {ssh_port}
Protocol 2
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes
AllowUsers {username}
AuthenticationMethods publickey
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
""".strip() + "\n"

    write_file(SSHD_DROPIN, config, ctx)

    fail2ban_jail = f"""
[sshd-raijin]
enabled = true
port    = {ssh_port}
filter  = sshd
logpath = /var/log/auth.log
maxretry = 5
findtime = 600
bantime  = 3600
""".strip() + "\n"
    write_file(FAIL2BAN_JAIL, fail2ban_jail, ctx)

    run_cmd(["sshd", "-t"], ctx)
    run_cmd(["systemctl", "enable", "ssh"], ctx)
    run_cmd(["systemctl", "restart", "ssh"], ctx)
    run_cmd(["systemctl", "restart", "fail2ban"], ctx, check=False)

    if ssh_port != "22":
        run_cmd(["ufw", "allow", ssh_port], ctx, check=False)
        run_cmd(["ufw", "delete", "allow", "22"], ctx, check=False)

    typer.secho("\n✓ SSH hardening concluido com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Usuario permitido: {username}")
    typer.echo(f"Porta configurada: {ssh_port}")
    typer.echo("Certifique-se de testar a nova sessao antes de encerrar conexoes atuais.")
