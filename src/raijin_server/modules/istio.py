"""Instalacao do Istio usando istioctl."""

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("istioctl", ctx, install_hint="Instale o binario do Istio CLI.")
    typer.echo("Instalando Istio (perfil raijin)...")
    run_cmd(["istioctl", "install", "--set", "profile=raijin", "-y"], ctx)
    run_cmd(["kubectl", "label", "namespace", "default", "istio-injection=enabled", "--overwrite"], ctx)
