"""Instalacao do Harness Delegate via Helm."""

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, require_root, run_cmd


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    ensure_tool("helm", ctx, install_hint="Instale helm para implantar o delegate.")

    typer.echo("Instalando Harness Delegate via Helm...")
    account_id = typer.prompt("Harness accountId")
    org_id = typer.prompt("Org ID", default="default")
    project_id = typer.prompt("Project ID", default="default")
    delegate_name = typer.prompt("Delegate name", default="raijin-delegate")
    namespace = typer.prompt("Namespace", default="harness-delegate")
    delegate_token = typer.prompt("Delegate token", hide_input=True)

    run_cmd(
        ["helm", "repo", "add", "harness", "https://app.harness.io/storage/harness-download/delegate-helm-chart/"],
        ctx,
    )
    run_cmd(["helm", "repo", "update"], ctx)

    cmd = [
        "helm",
        "upgrade",
        "--install",
        delegate_name,
        "harness/harness-delegate-ng",
        "-n",
        namespace,
        "--create-namespace",
        "--set",
        f"delegateName={delegate_name}",
        "--set",
        f"accountId={account_id}",
        "--set",
        f"delegateToken={delegate_token}",
        "--set",
        f"orgId={org_id}",
        "--set",
        f"projectId={project_id}",
    ]

    run_cmd(cmd, ctx, mask_output=True, display_override="helm upgrade --install <delegate> harness/harness-delegate-ng ...")
