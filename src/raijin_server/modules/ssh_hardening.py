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


def _current_non_root_user() -> str | None:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        return sudo_user
    try:
        import getpass

        who = getpass.getuser()
        return who if who != "root" else None
    except Exception:
        return None


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
    normalized_key = content.replace("\r\n", "\n").strip()  # normaliza CRLF de chaves geradas no Windows
    auth_file.write_text(AUTHORIZED_KEYS_TEMPLATE.format(key=normalized_key))
    os.chmod(auth_file, 0o600)
    run_cmd(["chown", "-R", f"{username}:{username}", str(ssh_dir)], ctx)


def _default_pubkey_path() -> Path:
    user = _current_non_root_user()
    if user:
        candidate = Path(f"/home/{user}/.ssh/authorized_keys")
        if candidate.exists():
            return candidate
    return Path.home() / ".ssh/authorized_keys"


def _load_public_key(path_input: str) -> str:
    path = Path(path_input).expanduser()
    if path.exists():
        content = path.read_text().strip()
        if content:
            return content
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

    username = typer.prompt("Usuario administrativo para SSH", default="thor")
    ssh_port = typer.prompt("Porta SSH", default="22")
    sudo_access = typer.confirm("Adicionar usuario ao grupo sudo?", default=True)
    current_user = _current_non_root_user()
    default_extra = current_user if current_user and current_user != username else ""
    extra_users_raw = typer.prompt(
        "Usuarios adicionais (serao criados se nao existirem, separados por espaco)",
        default=default_extra,
    ).strip()
    pubkey_path = typer.prompt(
        "Arquivo com chave publica ou authorized_keys existente",
        default=str(_default_pubkey_path()),
    )

    public_key = _load_public_key(pubkey_path)

    extra_users = [u for u in extra_users_raw.split() if u]
    target_users: list[str] = []
    for u in [username, *extra_users]:
        if u not in target_users:
            target_users.append(u)
    allow_users = " ".join(target_users)

    for user in target_users:
        _ensure_user(user, ctx)
        if user == username and sudo_access:
            run_cmd(["usermod", "-aG", "sudo", user], ctx)
        _write_authorized_keys(user, public_key, ctx)

    config = f"""
# Arquivo gerenciado pelo raijin-server
Port {ssh_port}
Protocol 2
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile %h/.ssh/authorized_keys
AllowUsers {allow_users}
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
