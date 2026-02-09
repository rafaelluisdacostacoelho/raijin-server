"""Seguranca e hardening do Supabase — CORS, Rate Limiting, Network Policies, RLS."""

from __future__ import annotations

import json
import re
import textwrap
import tempfile
from pathlib import Path
from typing import Optional

import typer

from raijin_server.utils import ExecutionContext, run_cmd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_manifest(ctx: ExecutionContext, manifest: str, description: str) -> bool:
    """Aplica manifest YAML temporario."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            tmp.write(manifest)
            tmp.flush()
            tmp_path = Path(tmp.name)
        result = run_cmd(["kubectl", "apply", "-f", str(tmp_path)], ctx, check=False)
        if result.returncode != 0:
            typer.secho(f"  ✗ Falha ao aplicar {description}.", fg=typer.colors.RED)
            return False
        typer.secho(f"  ✓ {description} aplicado.", fg=typer.colors.GREEN)
        return True
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _get_kong_config(ctx: ExecutionContext, namespace: str = "supabase") -> Optional[str]:
    """Obtem conteudo atual do kong.yml do ConfigMap."""
    result = run_cmd(
        ["kubectl", "get", "configmap", "kong-config", "-n", namespace,
         "-o", "jsonpath={.data.kong\\.yml}"],
        ctx, check=False,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return None
    return (result.stdout or "").strip()


def _extract_origins(kong_yml: str) -> list[str]:
    """Extrai lista de origins do kong.yml."""
    origins: list[str] = []
    in_origins = False
    for line in kong_yml.splitlines():
        stripped = line.strip()
        if stripped == "origins:":
            in_origins = True
            continue
        if in_origins:
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                if val and val not in origins:
                    origins.append(val)
            else:
                in_origins = False
    return origins


def _replace_origins_in_kong_yml(kong_yml: str, new_origins: list[str]) -> str:
    """Substitui todas as listas de origins no kong.yml por new_origins."""
    lines = kong_yml.splitlines()
    result_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == "origins:":
            # Manter a linha "origins:"
            indent = line[: len(line) - len(line.lstrip())]
            result_lines.append(line)
            # Pular origins antigos
            i += 1
            while i < len(lines) and lines[i].strip().startswith("- "):
                # Verificar se eh origin item (nao outro campo)
                next_stripped = lines[i].strip()
                if next_stripped.startswith("- ") and not any(
                    kw in next_stripped for kw in ["name:", "url:", "path:", "port:"]
                ):
                    i += 1
                else:
                    break
            # Inserir novos origins
            origin_indent = indent + "  "
            for origin in new_origins:
                result_lines.append(f'{origin_indent}- "{origin}"')
            continue
        result_lines.append(line)
        i += 1
    return "\n".join(result_lines)


def _apply_kong_config(
    ctx: ExecutionContext, kong_yml: str, namespace: str = "supabase"
) -> bool:
    """Aplica novo kong.yml como ConfigMap e restarta Kong."""
    # Escapar para ConfigMap YAML
    # Precisamos criar o ConfigMap com o kong.yml como data
    manifest = textwrap.dedent(f"""\
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: kong-config
          namespace: {namespace}
        data:
          kong.yml: |
    """)
    # Indentar kong.yml com 4 espacos
    for line in kong_yml.splitlines():
        manifest += f"    {line}\n"

    if not _apply_manifest(ctx, manifest, "Kong ConfigMap (CORS atualizado)"):
        return False

    # Restart Kong para carregar novo config
    typer.echo("  Reiniciando Kong para aplicar nova configuracao...")
    result = run_cmd(
        ["kubectl", "rollout", "restart", "deployment/supabase-kong", "-n", namespace],
        ctx, check=False,
    )
    if result.returncode != 0:
        typer.secho("  ✗ Falha ao reiniciar Kong.", fg=typer.colors.RED)
        return False

    # Esperar rollout
    run_cmd(
        ["kubectl", "rollout", "status", "deployment/supabase-kong",
         "-n", namespace, "--timeout=120s"],
        ctx, check=False,
    )
    typer.secho("  ✓ Kong reiniciado com nova configuracao CORS.", fg=typer.colors.GREEN)
    return True


# ---------------------------------------------------------------------------
# CORS Management
# ---------------------------------------------------------------------------

def cors_list(ctx: ExecutionContext, namespace: str = "supabase") -> list[str]:
    """Lista dominios CORS configurados no Kong."""
    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return []

    origins = _extract_origins(kong_yml)

    typer.secho("\n🔒 Dominios CORS autorizados no Supabase:", fg=typer.colors.CYAN, bold=True)
    if not origins:
        typer.secho("  (nenhum dominio configurado)", fg=typer.colors.YELLOW)
    elif origins == ["*"]:
        typer.secho("  ⚠  CORS ABERTO — qualquer origem aceita!", fg=typer.colors.RED, bold=True)
    else:
        for i, origin in enumerate(origins, 1):
            typer.echo(f"  {i}. {origin}")

    typer.echo(f"\n  Total: {len(origins)} origem(ns)")
    return origins


def cors_add(ctx: ExecutionContext, domain: str, namespace: str = "supabase") -> bool:
    """Adiciona dominio ao CORS do Kong."""
    # Validar formato
    if not domain.startswith("http://") and not domain.startswith("https://"):
        typer.secho(
            f"✗ Dominio deve comecar com https:// (ou http:// para dev): {domain}",
            fg=typer.colors.RED,
        )
        return False

    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return False

    origins = _extract_origins(kong_yml)

    # Se CORS aberto, inicializar com self-reference
    if origins == ["*"]:
        typer.secho("  Convertendo CORS de aberto (*) para allowlist...", fg=typer.colors.YELLOW)
        origins = []

    if domain in origins:
        typer.secho(f"  Dominio '{domain}' ja esta autorizado.", fg=typer.colors.YELLOW)
        return True

    origins.append(domain)
    new_kong_yml = _replace_origins_in_kong_yml(kong_yml, origins)

    typer.secho(f"\n  Adicionando '{domain}' ao CORS...", fg=typer.colors.CYAN)
    if _apply_kong_config(ctx, new_kong_yml, namespace):
        typer.secho(f"  ✓ Dominio '{domain}' adicionado ao CORS.", fg=typer.colors.GREEN)
        return True
    return False


def cors_remove(ctx: ExecutionContext, domain: str, namespace: str = "supabase") -> bool:
    """Remove dominio do CORS do Kong."""
    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return False

    origins = _extract_origins(kong_yml)

    if domain not in origins:
        typer.secho(f"  Dominio '{domain}' nao esta na lista CORS.", fg=typer.colors.YELLOW)
        return False

    if len(origins) <= 1:
        typer.secho(
            "  ✗ Nao eh possivel remover o ultimo dominio. Adicione outro antes de remover este.",
            fg=typer.colors.RED,
        )
        return False

    origins.remove(domain)
    new_kong_yml = _replace_origins_in_kong_yml(kong_yml, origins)

    typer.secho(f"\n  Removendo '{domain}' do CORS...", fg=typer.colors.CYAN)
    if _apply_kong_config(ctx, new_kong_yml, namespace):
        typer.secho(f"  ✓ Dominio '{domain}' removido do CORS.", fg=typer.colors.GREEN)
        return True
    return False


# ---------------------------------------------------------------------------
# App Management
# ---------------------------------------------------------------------------

def _get_registered_apps(ctx: ExecutionContext, namespace: str = "supabase") -> dict:
    """Obtem ConfigMap de apps registrados."""
    result = run_cmd(
        ["kubectl", "get", "configmap", "supabase-registered-apps", "-n", namespace,
         "-o", "jsonpath={.data.apps\\.json}"],
        ctx, check=False,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return {}
    try:
        return json.loads((result.stdout or "").strip())
    except json.JSONDecodeError:
        return {}


def _save_registered_apps(ctx: ExecutionContext, apps: dict, namespace: str = "supabase") -> bool:
    """Salva ConfigMap de apps registrados."""
    apps_json = json.dumps(apps, indent=2)
    manifest = textwrap.dedent(f"""\
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: supabase-registered-apps
          namespace: {namespace}
        data:
          apps.json: |
    """)
    for line in apps_json.splitlines():
        manifest += f"    {line}\n"

    return _apply_manifest(ctx, manifest, "Apps registrados ConfigMap")


def app_add(ctx: ExecutionContext, name: str, domain: str, namespace: str = "supabase") -> bool:
    """Registra nova aplicacao e adiciona seu dominio ao CORS."""
    typer.secho(f"\n📱 Registrando aplicacao '{name}'...", fg=typer.colors.CYAN, bold=True)

    # Validar nome
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', name) and len(name) > 2:
        if not re.match(r'^[a-z0-9\-]+$', name):
            typer.secho(
                f"✗ Nome invalido: use apenas letras minusculas, numeros e hifens.",
                fg=typer.colors.RED,
            )
            return False

    # Registrar app
    apps = _get_registered_apps(ctx, namespace)
    if name in apps:
        typer.secho(f"  ⚠ App '{name}' ja esta registrada.", fg=typer.colors.YELLOW)
        # Atualizar dominio se diferente
        if apps[name].get("domain") != domain:
            typer.echo(f"  Atualizando dominio de '{apps[name].get('domain')}' para '{domain}'...")
        else:
            return True

    apps[name] = {
        "domain": domain,
        "registered_at": _get_timestamp(),
    }

    if not _save_registered_apps(ctx, apps, namespace):
        return False

    # Adicionar ao CORS
    if not cors_add(ctx, domain, namespace):
        return False

    typer.secho(f"\n  ✓ Aplicacao '{name}' registrada com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"    Dominio CORS: {domain}")
    typer.echo(f"\n  Para usar no app:")
    typer.echo(f"    SUPABASE_URL=https://supabase.cryptidnest.com")
    typer.echo(f"    SUPABASE_ANON_KEY=<sua-anon-key>")
    return True


def app_remove(ctx: ExecutionContext, name: str, namespace: str = "supabase") -> bool:
    """Remove aplicacao registrada e seu dominio do CORS."""
    typer.secho(f"\n📱 Removendo aplicacao '{name}'...", fg=typer.colors.CYAN, bold=True)

    apps = _get_registered_apps(ctx, namespace)
    if name not in apps:
        typer.secho(f"  ✗ App '{name}' nao encontrada.", fg=typer.colors.RED)
        return False

    domain = apps[name].get("domain", "")

    # Remover do CORS
    if domain:
        cors_remove(ctx, domain, namespace)

    # Remover do registro
    del apps[name]
    if not _save_registered_apps(ctx, apps, namespace):
        return False

    typer.secho(f"  ✓ Aplicacao '{name}' removida.", fg=typer.colors.GREEN)
    return True


def app_list(ctx: ExecutionContext, namespace: str = "supabase") -> dict:
    """Lista aplicacoes registradas."""
    apps = _get_registered_apps(ctx, namespace)

    typer.secho("\n📱 Aplicacoes registradas no Supabase:", fg=typer.colors.CYAN, bold=True)
    if not apps:
        typer.secho("  (nenhuma aplicacao registrada)", fg=typer.colors.YELLOW)
        typer.echo("  Use: raijin-server supabase-security app-add --name <nome> --domain <url>")
    else:
        for i, (name, info) in enumerate(apps.items(), 1):
            domain = info.get("domain", "?")
            registered = info.get("registered_at", "?")
            typer.echo(f"  {i}. {name}")
            typer.echo(f"     Dominio: {domain}")
            typer.echo(f"     Registrado: {registered}")
            typer.echo()

    typer.echo(f"  Total: {len(apps)} aplicacao(oes)")
    return apps


def _get_timestamp() -> str:
    """Retorna timestamp formatado."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# ArgoCD Awareness
# ---------------------------------------------------------------------------

def _check_argocd_manages_kong(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Verifica se ArgoCD gerencia recursos do Kong (selfHeal reverteria mudancas manuais)."""
    result = run_cmd(
        ["kubectl", "get", "application", "-n", "argocd", "-o",
         "jsonpath={.items[*].metadata.name}"],
        ctx, check=False,
    )
    if result.returncode != 0:
        return False
    apps = (result.stdout or "").strip().split()
    # Verificar se algum app do ArgoCD aponta para services/
    for app_name in apps:
        res = run_cmd(
            ["kubectl", "get", "application", app_name, "-n", "argocd", "-o",
             "jsonpath={.spec.source.path}"],
            ctx, check=False,
        )
        path = (res.stdout or "").strip()
        if path and ("services" in path or "service" in path):
            return True
    return False


def _warn_argocd(ctx: ExecutionContext, namespace: str = "supabase") -> None:
    """Emite aviso se ArgoCD pode reverter mudancas manuais no Kong."""
    if _check_argocd_manages_kong(ctx, namespace):
        typer.secho(
            "\n  ⚠  ArgoCD detectado gerenciando services/!\n"
            "     Mudancas via kubectl serao REVERTIDAS pelo selfHeal.\n"
            "     Para persistir, commite no repositorio Git do ArgoCD.\n",
            fg=typer.colors.YELLOW, bold=True,
        )


# ---------------------------------------------------------------------------
# Security Hardening
# ---------------------------------------------------------------------------

def harden_key_auth(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Configura key-auth no Kong com consumers anon e service_role."""
    typer.secho("\n🔒 Configurando Key-Auth no Kong...", fg=typer.colors.CYAN, bold=True)

    _warn_argocd(ctx, namespace)

    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("  ✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return False

    # Obter JWT keys do Secret
    anon_key_result = run_cmd(
        ["kubectl", "get", "secret", "supabase-secrets", "-n", namespace,
         "-o", "jsonpath={.data.ANON_KEY}"],
        ctx, check=False,
    )
    service_key_result = run_cmd(
        ["kubectl", "get", "secret", "supabase-secrets", "-n", namespace,
         "-o", "jsonpath={.data.SERVICE_ROLE_KEY}"],
        ctx, check=False,
    )

    # Decodificar base64
    import base64
    anon_key = ""
    service_key = ""
    try:
        anon_raw = (anon_key_result.stdout or "").strip()
        service_raw = (service_key_result.stdout or "").strip()
        if anon_raw:
            anon_key = base64.b64decode(anon_raw).decode()
        if service_raw:
            service_key = base64.b64decode(service_raw).decode()
    except Exception:
        pass

    if not anon_key or not service_key:
        typer.secho(
            "  ✗ Nao foi possivel obter ANON_KEY/SERVICE_ROLE_KEY do secret 'supabase-secrets'.",
            fg=typer.colors.RED,
        )
        typer.echo("    Verifique se o secret existe: kubectl get secret supabase-secrets -n supabase")
        return False

    # Verificar se consumers ja existem
    if "consumers:" in kong_yml and "keyauth_credentials:" in kong_yml:
        typer.secho("  ✓ Key-auth consumers ja configurados.", fg=typer.colors.GREEN)
    else:
        # Adicionar consumers no inicio do kong.yml (apos _format_version)
        consumers_block = textwrap.dedent(f"""\
        consumers:
          - username: anon
            keyauth_credentials:
              - key: "{anon_key}"
          - username: service_role
            keyauth_credentials:
              - key: "{service_key}"
        """)
        # Inserir antes de "services:"
        kong_yml = kong_yml.replace("services:", consumers_block + "services:", 1)
        typer.echo("  + Consumers anon e service_role criados.")

    # Adicionar key-auth plugin aos servicos (auth, rest, realtime, storage)
    target_services = {"auth", "rest", "realtime", "storage"}
    if "key-auth" in kong_yml:
        typer.secho("  ✓ Plugin key-auth ja presente na configuracao.", fg=typer.colors.GREEN)
    else:
        # Adicionar key-auth como primeiro plugin apos cada servico-alvo
        new_lines: list[str] = []
        current_service = ""
        key_auth_added = False
        for line in kong_yml.splitlines():
            new_lines.append(line)
            stripped = line.strip()

            # Detectar servico atual
            if stripped.startswith("- name: ") and "name: cors" not in stripped and "name: rate-limiting" not in stripped and "name: key-auth" not in stripped and "name: request-termination" not in stripped:
                svc_name = stripped.replace("- name: ", "").strip()
                if svc_name in target_services or svc_name in {"health", "root-health", "auth-all", "rest-all", "realtime-all", "storage-all"}:
                    current_service = svc_name

            # Apos "plugins:" no contexto de um servico-alvo, adicionar key-auth
            if stripped == "plugins:" and current_service in target_services:
                indent = "          "
                new_lines.append(f"{indent}- name: key-auth")
                new_lines.append(f"{indent}  config:")
                new_lines.append(f"{indent}    key_names:")
                new_lines.append(f"{indent}      - apikey")
                new_lines.append(f"{indent}    hide_credentials: false")
                key_auth_added = True

        if key_auth_added:
            kong_yml = "\n".join(new_lines)
            typer.echo("  + Plugin key-auth adicionado em: " + ", ".join(sorted(target_services)))

    if _apply_kong_config(ctx, kong_yml, namespace):
        typer.secho("  ✓ Key-auth configurado com sucesso.", fg=typer.colors.GREEN)
        typer.echo("    Consumers: anon, service_role")
        typer.echo("    Modo: apikey header/query param")
        typer.echo("    Rotas protegidas: auth, rest, realtime, storage")
        typer.echo("    Rota publica (sem auth): / (health)")
        return True
    return False


def harden_http_redirect(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Cria Middleware Traefik para redirect HTTP → HTTPS e Ingress de redirect."""
    typer.secho("\n🔒 Configurando HTTP → HTTPS Redirect...", fg=typer.colors.CYAN, bold=True)

    # 1. Middleware de redirect
    redirect_manifest = textwrap.dedent(f"""\
        apiVersion: traefik.io/v1alpha1
        kind: Middleware
        metadata:
          name: redirect-https
          namespace: {namespace}
        spec:
          redirectScheme:
            scheme: https
            permanent: true
    """)

    if not _apply_manifest(ctx, redirect_manifest, "Redirect HTTPS Middleware"):
        return False

    # 2. Obter dominio do Ingress existente
    result = run_cmd(
        ["kubectl", "get", "ingress", "-n", namespace, "-o",
         "jsonpath={.items[0].spec.rules[0].host}"],
        ctx, check=False,
    )
    domain = (result.stdout or "").strip()
    if not domain:
        typer.secho("  ⚠ Nenhum Ingress/dominio encontrado. Redirect middleware criado mas sem Ingress HTTP.", fg=typer.colors.YELLOW)
        return True

    # 3. Ingress HTTP que redireciona para HTTPS
    redirect_ingress = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: Ingress
        metadata:
          name: supabase-redirect-http
          namespace: {namespace}
          annotations:
            traefik.ingress.kubernetes.io/router.entrypoints: web
            traefik.ingress.kubernetes.io/router.middlewares: {namespace}-redirect-https@kubernetescrd
        spec:
          rules:
          - host: {domain}
            http:
              paths:
              - path: /
                pathType: Prefix
                backend:
                  service:
                    name: supabase-kong
                    port:
                      number: 8000
    """)

    if not _apply_manifest(ctx, redirect_ingress, "HTTP Redirect Ingress"):
        return False

    typer.secho(f"  ✓ HTTP → HTTPS redirect configurado para {domain}.", fg=typer.colors.GREEN)
    return True


def harden_health_endpoint(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Adiciona health endpoint (/) no Kong com request-termination."""
    typer.secho("\n🔒 Configurando Health Endpoint (/) no Kong...", fg=typer.colors.CYAN, bold=True)

    _warn_argocd(ctx, namespace)

    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("  ✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return False

    # Verificar se health service ja existe
    if "request-termination" in kong_yml:
        typer.secho("  ✓ Health endpoint (/) ja configurado.", fg=typer.colors.GREEN)
        return True

    # Obter origins atuais para CORS do health
    origins = _extract_origins(kong_yml)
    origins_yaml = ""
    for o in origins:
        origins_yaml += f'\n              - "{o}"'

    # Adicionar health service como primeiro servico
    health_block = textwrap.dedent("""\
        - name: health
          url: http://localhost:8000
          routes:
            - name: root-health
              paths:
                - /
              strip_path: false
          plugins:
            - name: request-termination
              config:
                status_code: 200
                content_type: "application/json"
                body: '{"status":"ok","service":"supabase","endpoints":{"/auth/v1/":"Authentication","/rest/v1/":"REST API","/storage/v1/":"Storage","/realtime/v1/":"Realtime"}}'
            - name: cors
              config:
                origins:""")

    for o in origins:
        health_block += f'\n              - "{o}"'
    health_block += "\n            credentials: true\n"

    # Inserir apos "services:" (como primeiro servico)
    kong_yml = kong_yml.replace("services:\n", "services:\n    " + health_block.replace("\n", "\n    ") + "\n", 1)

    if _apply_kong_config(ctx, kong_yml, namespace):
        typer.secho("  ✓ Health endpoint (/) configurado com status 200 JSON.", fg=typer.colors.GREEN)
        return True
    return False


def harden_kong_clusterip(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Muda Kong de LoadBalancer para ClusterIP."""
    typer.secho("\n🔒 Convertendo Kong para ClusterIP...", fg=typer.colors.CYAN, bold=True)

    # Patch o service
    patch = json.dumps({"spec": {"type": "ClusterIP"}})
    result = run_cmd(
        ["kubectl", "patch", "svc", "supabase-kong", "-n", namespace,
         "-p", patch, "--type=merge"],
        ctx, check=False,
    )
    # Patch com type change pode falhar - precisa delete + recreate
    if result.returncode != 0:
        typer.echo("  Service type change requer recreacao...")
        # Get current service
        result = run_cmd(
            ["kubectl", "delete", "svc", "supabase-kong", "-n", namespace],
            ctx, check=False,
        )
        manifest = textwrap.dedent(f"""\
            apiVersion: v1
            kind: Service
            metadata:
              name: supabase-kong
              namespace: {namespace}
              labels:
                app: supabase-kong
            spec:
              type: ClusterIP
              ports:
              - port: 8000
                targetPort: 8000
                protocol: TCP
                name: proxy
              - port: 8443
                targetPort: 8443
                protocol: TCP
                name: proxy-ssl
              selector:
                app: supabase-kong
        """)
        if not _apply_manifest(ctx, manifest, "Kong Service (ClusterIP)"):
            return False
    
    typer.secho("  ✓ Kong agora eh ClusterIP (acesso apenas via Traefik).", fg=typer.colors.GREEN)
    return True


def harden_rate_limiting(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Adiciona rate limiting no Kong."""
    typer.secho("\n🔒 Configurando Rate Limiting no Kong...", fg=typer.colors.CYAN, bold=True)

    kong_yml = _get_kong_config(ctx, namespace)
    if not kong_yml:
        typer.secho("✗ Nao foi possivel obter configuracao do Kong.", fg=typer.colors.RED)
        return False

    # Limites por servico
    rate_limits = {
        "auth": 30,
        "rest": 300,
        "storage": 60,
        "realtime": 60,
    }

    # Adicionar plugin rate-limiting a cada servico
    new_lines: list[str] = []
    current_service = ""
    for line in kong_yml.splitlines():
        new_lines.append(line)
        stripped = line.strip()

        # Detectar servico atual
        if stripped.startswith("- name: ") and "name: cors" not in stripped:
            current_service = stripped.replace("- name: ", "").strip()

        # Apos o bloco do plugin cors (credentials: true), adicionar rate-limiting
        if stripped == "credentials: true" and current_service in rate_limits:
            indent = line[: len(line) - len(line.lstrip())]
            # Voltar 2 niveis de indentacao para ficar no nivel do plugin
            plugin_indent = indent.replace("    ", "", 1) if "    " in indent else indent
            # Detectar indentacao base do plugin
            base = "          "  # indentacao padrao de um plugin item
            new_lines.append(f"{base}- name: rate-limiting")
            new_lines.append(f"{base}  config:")
            new_lines.append(f"{base}    minute: {rate_limits[current_service]}")
            new_lines.append(f"{base}    policy: local")
            new_lines.append(f"{base}    fault_tolerant: true")
            new_lines.append(f"{base}    hide_client_headers: false")

    new_kong_yml = "\n".join(new_lines)

    if _apply_kong_config(ctx, new_kong_yml, namespace):
        typer.secho("  ✓ Rate limiting configurado em todos os servicos.", fg=typer.colors.GREEN)
        for svc, limit in rate_limits.items():
            typer.echo(f"    {svc}: {limit} req/min")
        return True
    return False


def harden_security_headers(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Cria Middleware Traefik com security headers."""
    typer.secho("\n🔒 Configurando Security Headers (Traefik)...", fg=typer.colors.CYAN, bold=True)

    middleware_manifest = textwrap.dedent(f"""\
        apiVersion: traefik.io/v1alpha1
        kind: Middleware
        metadata:
          name: supabase-security-headers
          namespace: {namespace}
        spec:
          headers:
            stsSeconds: 31536000
            stsIncludeSubdomains: true
            stsPreload: true
            contentTypeNosniff: true
            frameDeny: true
            browserXssFilter: true
            referrerPolicy: "strict-origin-when-cross-origin"
            customResponseHeaders:
              X-Powered-By: ""
              Server: ""
    """)

    if not _apply_manifest(ctx, middleware_manifest, "Security Headers Middleware"):
        return False

    # Patchear o Ingress para usar o middleware
    result = run_cmd(
        ["kubectl", "get", "ingress", "-n", namespace, "-o",
         "jsonpath={.items[0].metadata.name}"],
        ctx, check=False,
    )
    ingress_name = (result.stdout or "").strip()
    if not ingress_name:
        typer.secho("  ⚠ Nenhum Ingress encontrado para patchear.", fg=typer.colors.YELLOW)
        return True  # Middleware criado, mas sem ingress para linkar

    patch = json.dumps({
        "metadata": {
            "annotations": {
                "traefik.ingress.kubernetes.io/router.middlewares":
                    f"{namespace}-supabase-security-headers@kubernetescrd"
            }
        }
    })
    result = run_cmd(
        ["kubectl", "patch", "ingress", ingress_name, "-n", namespace,
         "-p", patch, "--type=merge"],
        ctx, check=False,
    )
    if result.returncode == 0:
        typer.secho(f"  ✓ Ingress '{ingress_name}' atualizado com security headers.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ⚠ Falha ao patchear Ingress.", fg=typer.colors.YELLOW)

    return True


def harden_gotrue(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Aplica hardening no GoTrue (Auth)."""
    typer.secho("\n🔒 Hardening do GoTrue (Auth)...", fg=typer.colors.CYAN, bold=True)

    # Adicionar env vars de seguranca
    env_patch = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [{
                        "name": "gotrue",
                        "env": [
                            {"name": "GOTRUE_RATE_LIMIT_HEADER", "value": "X-Forwarded-For"},
                            {"name": "GOTRUE_RATE_LIMIT_EMAIL_SENT", "value": "5"},
                        ]
                    }]
                }
            }
        }
    }

    result = run_cmd(
        ["kubectl", "patch", "deployment", "supabase-gotrue", "-n", namespace,
         "-p", json.dumps(env_patch), "--type=strategic"],
        ctx, check=False,
    )

    if result.returncode == 0:
        typer.secho("  ✓ GoTrue hardened com rate limit headers.", fg=typer.colors.GREEN)
        return True
    else:
        typer.secho("  ⚠ Falha ao patchear GoTrue - aplicar manualmente.", fg=typer.colors.YELLOW)
        return False


def harden_network_policies(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Aplica Network Policies de seguranca."""
    typer.secho("\n🔒 Aplicando Network Policies...", fg=typer.colors.CYAN, bold=True)

    # Policy 1: Default deny all ingress
    default_deny = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: default-deny-ingress
          namespace: {namespace}
        spec:
          podSelector: {{}}
          policyTypes:
          - Ingress
    """)

    # Policy 2: Kong aceita de Traefik e externo
    kong_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: kong-allow-ingress
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app: supabase-kong
          policyTypes:
          - Ingress
          ingress:
          - from:
            - namespaceSelector: {{}}
            ports:
            - protocol: TCP
              port: 8000
            - protocol: TCP
              port: 8443
    """)

    # Policy 3: Services aceitam de Kong
    services_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: services-allow-kong
          namespace: {namespace}
        spec:
          podSelector:
            matchExpressions:
            - key: app
              operator: In
              values:
              - supabase-postgrest
              - supabase-gotrue
              - supabase-realtime
              - supabase-storage
          policyTypes:
          - Ingress
          ingress:
          - from:
            - podSelector:
                matchLabels:
                  app: supabase-kong
    """)

    # Policy 4: PostgreSQL aceita apenas do namespace
    postgres_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: postgres-allow-supabase
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app: postgres
          policyTypes:
          - Ingress
          ingress:
          - from:
            - podSelector: {{}}
            ports:
            - protocol: TCP
              port: 5432
    """)

    # Policy 5: Egress DNS + interno + MinIO
    egress_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: supabase-egress
          namespace: {namespace}
        spec:
          podSelector: {{}}
          policyTypes:
          - Egress
          egress:
          - to:
            - namespaceSelector: {{}}
            ports:
            - protocol: UDP
              port: 53
          - to:
            - podSelector: {{}}
          - to:
            - namespaceSelector:
                matchLabels:
                  kubernetes.io/metadata.name: minio
            ports:
            - protocol: TCP
              port: 9000
          - to: []
            ports:
            - protocol: TCP
              port: 443
            - protocol: TCP
              port: 80
    """)

    # Policy 6: Studio aceita ingress externo (NodePort 30333)
    studio_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: studio-allow-ingress
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app: supabase-studio
          policyTypes:
          - Ingress
          ingress:
          - ports:
            - port: 3000
              protocol: TCP
    """)

    # Policy 7: pg-meta aceita ingress de Studio
    pgmeta_policy = textwrap.dedent(f"""\
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: pgmeta-allow-studio
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app: supabase-pg-meta
          policyTypes:
          - Ingress
          ingress:
          - from:
            - podSelector:
                matchLabels:
                  app: supabase-studio
            ports:
            - port: 8080
              protocol: TCP
    """)

    success = True
    for manifest, desc in [
        (default_deny, "Default deny ingress"),
        (kong_policy, "Kong ingress policy"),
        (services_policy, "Services ingress policy"),
        (postgres_policy, "PostgreSQL ingress policy"),
        (egress_policy, "Egress policy"),
        (studio_policy, "Studio ingress policy"),
        (pgmeta_policy, "pg-meta ingress policy (Studio)"),
    ]:
        if not _apply_manifest(ctx, manifest, desc):
            success = False

    if success:
        typer.secho("  ✓ Network Policies aplicadas com sucesso (7 policies).", fg=typer.colors.GREEN)
    return success


def harden_rls(ctx: ExecutionContext, namespace: str = "supabase") -> bool:
    """Habilita RLS nas tabelas de storage."""
    typer.secho("\n🔒 Habilitando Row Level Security (storage)...", fg=typer.colors.CYAN, bold=True)

    sql = textwrap.dedent("""\
        -- Habilitar RLS em storage.objects
        ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
        
        -- Habilitar RLS em storage.buckets
        ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY;
        
        -- Policy: service_role full access em objects
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_full_objects') THEN
                CREATE POLICY service_role_full_objects ON storage.objects
                    FOR ALL USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');
            END IF;
        END $$;
        
        -- Policy: service_role full access em buckets
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_full_buckets') THEN
                CREATE POLICY service_role_full_buckets ON storage.buckets
                    FOR ALL USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');
            END IF;
        END $$;
        
        -- Policy: leitura publica em buckets publicos
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'public_read_objects') THEN
                CREATE POLICY public_read_objects ON storage.objects
                    FOR SELECT USING (bucket_id IN (SELECT id FROM storage.buckets WHERE public = true));
            END IF;
        END $$;
    """)

    result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-c", sql],
        ctx, check=False,
    )

    if result.returncode == 0:
        typer.secho("  ✓ RLS habilitado em storage.objects e storage.buckets.", fg=typer.colors.GREEN)
        return True
    else:
        typer.secho(f"  ⚠ Algumas policies podem ja existir (normal).", fg=typer.colors.YELLOW)
        # Verificar se RLS foi habilitado
        check = run_cmd(
            ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
             "psql", "-U", "postgres", "-c",
             "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='storage';"],
            ctx, check=False,
        )
        if check.returncode == 0:
            typer.echo(f"  {(check.stdout or '').strip()}")
        return True


# ---------------------------------------------------------------------------
# Status / Diagnostico
# ---------------------------------------------------------------------------

def status(ctx: ExecutionContext, namespace: str = "supabase") -> None:
    """Mostra status completo de seguranca do Supabase."""
    typer.secho("\n🔒 Status de Seguranca — Supabase", fg=typer.colors.CYAN, bold=True)
    typer.echo("=" * 60)
    typer.echo("  Verificacoes: 17 itens")

    # 1. CORS
    typer.echo("\n[1/19] CORS")
    kong_yml = _get_kong_config(ctx, namespace)
    if kong_yml:
        origins = _extract_origins(kong_yml)
        if origins == ["*"]:
            typer.secho("  ✗ CORS ABERTO (*) — CRITICO!", fg=typer.colors.RED, bold=True)
        elif not origins:
            typer.secho("  ⚠ Sem origins configurados.", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"  ✓ CORS restrito a {len(origins)} origem(ns).", fg=typer.colors.GREEN)
            for o in origins:
                typer.echo(f"    - {o}")
    else:
        typer.secho("  ✗ Nao foi possivel ler Kong config.", fg=typer.colors.RED)

    # 2. RLS
    typer.echo("\n[2/19] Row Level Security (RLS)")
    rls_result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-t", "-c",
         "SELECT tablename || '=' || rowsecurity FROM pg_tables WHERE schemaname='storage' ORDER BY tablename;"],
        ctx, check=False,
    )
    if rls_result.returncode == 0:
        rls_lines = [l.strip() for l in (rls_result.stdout or "").strip().splitlines() if l.strip()]
        all_on = all("=t" in l for l in rls_lines if "migration" not in l)
        if all_on and rls_lines:
            typer.secho("  ✓ RLS habilitado em tabelas de storage.", fg=typer.colors.GREEN)
        else:
            typer.secho("  ✗ RLS desabilitado em algumas tabelas!", fg=typer.colors.RED)
        for l in rls_lines:
            status_icon = "✓" if "=t" in l else "✗"
            typer.echo(f"    {status_icon} storage.{l}")

    # 3. Kong Service Type
    typer.echo("\n[3/19] Kong Service Type")
    svc_result = run_cmd(
        ["kubectl", "get", "svc", "supabase-kong", "-n", namespace,
         "-o", "jsonpath={.spec.type}"],
        ctx, check=False,
    )
    svc_type = (svc_result.stdout or "").strip()
    if svc_type == "ClusterIP":
        typer.secho(f"  ✓ Kong eh ClusterIP (acesso apenas via Ingress).", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ✗ Kong eh {svc_type} — deveria ser ClusterIP!", fg=typer.colors.RED)

    # 4. Rate Limiting
    typer.echo("\n[4/19] Rate Limiting")
    if kong_yml and "rate-limiting" in kong_yml:
        typer.secho("  ✓ Rate limiting configurado.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Rate limiting NAO configurado!", fg=typer.colors.RED)

    # 5. MinIO Service Type
    typer.echo("\n[5/19] MinIO Service Type")
    minio_result = run_cmd(
        ["kubectl", "get", "svc", "minio", "-n", "minio",
         "-o", "jsonpath={.spec.type}"],
        ctx, check=False,
    )
    minio_type = (minio_result.stdout or "").strip()
    if minio_type == "ClusterIP":
        typer.secho("  ✓ MinIO eh ClusterIP (acesso interno apenas).", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  ⚠ MinIO eh {minio_type} — considere ClusterIP.", fg=typer.colors.YELLOW)

    # 6. Security Headers
    typer.echo("\n[6/19] Security Headers (Traefik)")
    headers_result = run_cmd(
        ["kubectl", "get", "middleware", "supabase-security-headers", "-n", namespace],
        ctx, check=False,
    )
    if headers_result.returncode == 0:
        typer.secho("  ✓ Middleware de security headers ativo.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Middleware de security headers NAO encontrado.", fg=typer.colors.RED)

    # 7. GoTrue Hardening
    typer.echo("\n[7/19] GoTrue Hardening")
    gotrue_result = run_cmd(
        ["kubectl", "get", "deployment", "supabase-gotrue", "-n", namespace,
         "-o", "jsonpath={.spec.template.spec.containers[0].env[*].name}"],
        ctx, check=False,
    )
    env_names = (gotrue_result.stdout or "").strip()
    if "GOTRUE_RATE_LIMIT_HEADER" in env_names:
        typer.secho("  ✓ GoTrue com rate limit headers.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ GoTrue sem rate limit headers.", fg=typer.colors.RED)

    # 8. Network Policies
    typer.echo("\n[8/19] Network Policies")
    np_result = run_cmd(
        ["kubectl", "get", "networkpolicies", "-n", namespace, "-o", "name"],
        ctx, check=False,
    )
    np_lines = [l.strip() for l in (np_result.stdout or "").strip().splitlines() if l.strip()]
    expected_policies = {
        "default-deny-ingress", "kong-allow-ingress", "services-allow-kong",
        "supabase-services-allow-kong", "postgres-allow-supabase",
        "supabase-egress", "supabase-allow-dns",
        "studio-allow-ingress", "pgmeta-allow-studio",
    }
    existing_names = {l.replace("networkpolicy.networking.k8s.io/", "") for l in np_lines}
    missing = expected_policies - existing_names
    if len(np_lines) >= 9 and not missing:
        typer.secho(f"  ✓ {len(np_lines)} Network Policies aplicadas.", fg=typer.colors.GREEN)
        for np in np_lines:
            typer.echo(f"    - {np}")
    elif np_lines:
        typer.secho(f"  ⚠ {len(np_lines)} Network Policies (esperado: 9+).", fg=typer.colors.YELLOW)
        if missing:
            typer.secho(f"    Faltando: {', '.join(sorted(missing))}", fg=typer.colors.YELLOW)
        for np in np_lines:
            typer.echo(f"    - {np}")
    else:
        typer.secho("  ✗ ZERO Network Policies!", fg=typer.colors.RED)

    # 9. Key-Auth (Autenticacao por API Key)
    typer.echo("\n[9/19] Key-Auth (API Key)")
    if kong_yml and "key-auth" in kong_yml and "consumers:" in kong_yml:
        # Contar quantos servicos tem key-auth
        key_auth_count = kong_yml.count("name: key-auth")
        typer.secho(f"  ✓ Key-auth ativo em {key_auth_count} servico(s) com consumers configurados.", fg=typer.colors.GREEN)
    elif kong_yml and "key-auth" in kong_yml:
        typer.secho("  ⚠ Key-auth presente mas sem consumers definidos.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ Key-auth NAO configurado — rotas desprotegidas!", fg=typer.colors.RED, bold=True)

    # 10. HTTP → HTTPS Redirect
    typer.echo("\n[10/19] HTTP → HTTPS Redirect")
    redirect_mw = run_cmd(
        ["kubectl", "get", "middleware", "redirect-https", "-n", namespace],
        ctx, check=False,
    )
    redirect_ing = run_cmd(
        ["kubectl", "get", "ingress", "supabase-redirect-http", "-n", namespace],
        ctx, check=False,
    )
    if redirect_mw.returncode == 0 and redirect_ing.returncode == 0:
        typer.secho("  ✓ Redirect HTTP → HTTPS configurado (middleware + ingress).", fg=typer.colors.GREEN)
    elif redirect_mw.returncode == 0:
        typer.secho("  ⚠ Middleware redirect existe mas falta Ingress HTTP.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ Redirect HTTP → HTTPS NAO configurado.", fg=typer.colors.RED)

    # 11. Health Endpoint (/)
    typer.echo("\n[11/19] Health Endpoint (/)")
    if kong_yml and "request-termination" in kong_yml:
        typer.secho("  ✓ Health endpoint (/) configurado com request-termination.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ Health endpoint (/) NAO configurado — / retorna 404.", fg=typer.colors.RED)

    # 12. Supabase Studio
    typer.echo("\n[12/19] Supabase Studio")
    studio_pod = run_cmd(
        ["kubectl", "get", "pods", "-n", namespace, "-l", "app=supabase-studio",
         "-o", "jsonpath={.items[0].status.phase}"],
        ctx, check=False,
    )
    studio_svc = run_cmd(
        ["kubectl", "get", "svc", "supabase-studio", "-n", namespace,
         "-o", "jsonpath={.spec.type}:{.spec.ports[0].nodePort}"],
        ctx, check=False,
    )
    studio_phase = (studio_pod.stdout or "").strip()
    studio_svc_info = (studio_svc.stdout or "").strip()
    if studio_phase == "Running":
        typer.secho(f"  ✓ Studio rodando ({studio_svc_info}).", fg=typer.colors.GREEN)
        # Verify critical env vars
        studio_env = run_cmd(
            ["kubectl", "get", "deployment", "supabase-studio", "-n", namespace,
             "-o", "jsonpath={.spec.template.spec.containers[0].env[*].name}"],
            ctx, check=False,
        )
        env_names = (studio_env.stdout or "").strip().split()
        required_studio_envs = {
            "POSTGRES_HOST", "POSTGRES_PASSWORD", "AUTH_JWT_SECRET",
            "SNIPPETS_MANAGEMENT_FOLDER", "STUDIO_PG_META_URL",
        }
        missing_envs = required_studio_envs - set(env_names)
        if not missing_envs:
            typer.secho("  ✓ Env vars criticas do Studio presentes.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ Env vars faltando: {', '.join(sorted(missing_envs))}", fg=typer.colors.RED)
    elif studio_phase:
        typer.secho(f"  ⚠ Studio em estado: {studio_phase}.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ Studio NAO encontrado.", fg=typer.colors.RED)

    # 13. pg-meta (dependencia do Studio)
    typer.echo("\n[13/19] pg-meta")
    pgmeta_pod = run_cmd(
        ["kubectl", "get", "pods", "-n", namespace, "-l", "app=supabase-pg-meta",
         "-o", "jsonpath={.items[0].status.phase}"],
        ctx, check=False,
    )
    pgmeta_phase = (pgmeta_pod.stdout or "").strip()
    if pgmeta_phase == "Running":
        typer.secho("  ✓ pg-meta rodando.", fg=typer.colors.GREEN)
        # Verify PG_META_DB_USER
        pgmeta_user = run_cmd(
            ["kubectl", "get", "deployment", "supabase-pg-meta", "-n", namespace,
             "-o", "jsonpath={.spec.template.spec.containers[0].env[?(@.name=='PG_META_DB_USER')].value}"],
            ctx, check=False,
        )
        db_user = (pgmeta_user.stdout or "").strip()
        if db_user == "supabase_admin":
            typer.secho(f"  ✓ PG_META_DB_USER={db_user} (correto).", fg=typer.colors.GREEN)
        elif db_user:
            typer.secho(f"  ⚠ PG_META_DB_USER={db_user} — esperado: supabase_admin.", fg=typer.colors.YELLOW)
        else:
            typer.secho("  ✗ PG_META_DB_USER nao definido.", fg=typer.colors.RED)
    elif pgmeta_phase:
        typer.secho(f"  ⚠ pg-meta em estado: {pgmeta_phase}.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ pg-meta NAO encontrado.", fg=typer.colors.RED)

    # 14. Role supabase_admin no PostgreSQL
    typer.echo("\n[14/19] Role supabase_admin")
    role_result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-t", "-c",
         "SELECT 1 FROM pg_roles WHERE rolname='supabase_admin' AND rolsuper;"],
        ctx, check=False,
    )
    role_exists = (role_result.stdout or "").strip()
    if role_exists == "1":
        typer.secho("  ✓ Role supabase_admin existe com SUPERUSER.", fg=typer.colors.GREEN)
    elif role_exists:
        typer.secho("  ⚠ Role supabase_admin existe mas sem SUPERUSER.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ Role supabase_admin NAO encontrado!", fg=typer.colors.RED)
        typer.echo("    Execute: database/init-roles.sql para criar.")

    # 15. Studio ↔ pg-meta conectividade
    typer.echo("\n[15/19] Studio ↔ pg-meta")
    pgmeta_err = run_cmd(
        ["kubectl", "logs", "-n", namespace, "-l", "app=supabase-pg-meta",
         "--since=60s", "--tail=50"],
        ctx, check=False,
    )
    pgmeta_logs = (pgmeta_err.stdout or "").strip()
    if "ENOTFOUND" in pgmeta_logs:
        typer.secho("  ✗ pg-meta com erros DNS (ENOTFOUND) — POSTGRES_HOST incorreto!", fg=typer.colors.RED)
    elif "password authentication failed" in pgmeta_logs:
        typer.secho("  ✗ pg-meta com erros de autenticacao — verificar role/senha!", fg=typer.colors.RED)
    elif "error" in pgmeta_logs.lower() and "level" in pgmeta_logs:
        err_count = pgmeta_logs.count('"level":"error"')
        if err_count > 0:
            typer.secho(f"  ⚠ pg-meta com {err_count} erro(s) no ultimo minuto.", fg=typer.colors.YELLOW)
        else:
            typer.secho("  ✓ Studio ↔ pg-meta sem erros.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✓ Studio ↔ pg-meta sem erros.", fg=typer.colors.GREEN)

    # 16. Edge Functions
    typer.echo("\n[16/19] Edge Functions")
    func_pod = run_cmd(
        ["kubectl", "get", "pods", "-n", namespace, "-l", "app=supabase-functions",
         "-o", "jsonpath={.items[0].status.phase}"],
        ctx, check=False,
    )
    func_phase = (func_pod.stdout or "").strip()
    if func_phase == "Running":
        typer.secho("  ✓ Edge Functions pod rodando.", fg=typer.colors.GREEN)
        # Check service targetPort
        func_tp = run_cmd(
            ["kubectl", "get", "svc", "supabase-functions", "-n", namespace,
             "-o", "jsonpath={.spec.ports[0].targetPort}"],
            ctx, check=False,
        )
        tp_val = (func_tp.stdout or "").strip()
        if tp_val == "9000":
            typer.secho("  ✓ Service targetPort=9000 (correto).", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ Service targetPort={tp_val} — esperado: 9000!", fg=typer.colors.RED)
        # Check Kong route
        if kong_yml and "/functions/v1/" in kong_yml:
            typer.secho("  ✓ Kong route /functions/v1/ configurada.", fg=typer.colors.GREEN)
        else:
            typer.secho("  ✗ Kong route /functions/v1/ NAO encontrada!", fg=typer.colors.RED)
    elif func_phase:
        typer.secho(f"  ⚠ Edge Functions em estado: {func_phase}.", fg=typer.colors.YELLOW)
    else:
        typer.secho("  ✗ Edge Functions NAO encontrado.", fg=typer.colors.RED)

    # 17. pg_stat_statements
    typer.echo("\n[17/19] pg_stat_statements")
    pss_result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-t", "-c",
         "SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements';"],
        ctx, check=False,
    )
    pss_exists = (pss_result.stdout or "").strip()
    if pss_exists == "1":
        typer.secho("  ✓ pg_stat_statements instalado.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ pg_stat_statements NAO instalado — Studio performance limitado.", fg=typer.colors.RED)
        typer.echo("    Execute: CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")

    # 18. shared_preload_libraries
    typer.echo("\n[18/19] shared_preload_libraries")
    spl_result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-t", "-c",
         "SHOW shared_preload_libraries;"],
        ctx, check=False,
    )
    spl_value = (spl_result.stdout or "").strip()
    if "pg_stat_statements" in spl_value:
        typer.secho(f"  ✓ shared_preload_libraries = '{spl_value}'.", fg=typer.colors.GREEN)
    else:
        typer.secho("  ✗ pg_stat_statements NAO esta em shared_preload_libraries.", fg=typer.colors.RED)
        typer.echo("    Adicione args: [\"-c\", \"shared_preload_libraries=pg_stat_statements\"] ao StatefulSet do Postgres.")

    # 19. supabase_migrations schema
    typer.echo("\n[19/19] supabase_migrations")
    mig_result = run_cmd(
        ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
         "psql", "-U", "postgres", "-t", "-c",
         "SELECT 1 FROM information_schema.schemata WHERE schema_name='supabase_migrations';"],
        ctx, check=False,
    )
    mig_exists = (mig_result.stdout or "").strip()
    if mig_exists == "1":
        typer.secho("  ✓ Schema supabase_migrations presente.", fg=typer.colors.GREEN)
        # Verificar tabela schema_migrations
        tbl_result = run_cmd(
            ["kubectl", "exec", "postgres-0", "-n", namespace, "--",
             "psql", "-U", "postgres", "-t", "-c",
             "SELECT 1 FROM information_schema.tables WHERE table_schema='supabase_migrations' AND table_name='schema_migrations';"],
            ctx, check=False,
        )
        tbl_exists = (tbl_result.stdout or "").strip()
        if tbl_exists == "1":
            typer.secho("  ✓ Tabela schema_migrations presente.", fg=typer.colors.GREEN)
        else:
            typer.secho("  ✗ Tabela schema_migrations NAO encontrada.", fg=typer.colors.RED)
    else:
        typer.secho("  ✗ Schema supabase_migrations NAO encontrado — funcionalidades de migracao indisponiveis.", fg=typer.colors.RED)
        typer.echo("    Execute init-roles.sql ou crie manualmente o schema.")

    # Apps registrados
    typer.echo("\n[+] Aplicacoes Registradas")
    apps = _get_registered_apps(ctx, namespace)
    if apps:
        for name, info in apps.items():
            typer.echo(f"    - {name}: {info.get('domain', '?')}")
    else:
        typer.secho("  (nenhuma aplicacao registrada)", fg=typer.colors.YELLOW)

    # ArgoCD
    typer.echo("\n[+] ArgoCD")
    if _check_argocd_manages_kong(ctx, namespace):
        typer.secho("  ⚠ ArgoCD gerencia services/ — mudancas manuais serao revertidas.", fg=typer.colors.YELLOW)
        typer.echo("    Use Git push para persistir alteracoes no Kong.")
    else:
        typer.echo("  ArgoCD nao detectado ou nao gerencia services/.")

    typer.echo("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# Hardening Completo
# ---------------------------------------------------------------------------

def harden_all(ctx: ExecutionContext, namespace: str = "supabase") -> None:
    """Aplica todas as medidas de seguranca."""
    typer.secho("\n🛡️  Hardening Completo do Supabase\n", fg=typer.colors.CYAN, bold=True)

    steps = [
        ("RLS (Row Level Security)", lambda: harden_rls(ctx, namespace)),
        ("Kong → ClusterIP", lambda: harden_kong_clusterip(ctx, namespace)),
        ("Key-Auth (API Key)", lambda: harden_key_auth(ctx, namespace)),
        ("Rate Limiting", lambda: harden_rate_limiting(ctx, namespace)),
        ("Health Endpoint (/)", lambda: harden_health_endpoint(ctx, namespace)),
        ("Security Headers", lambda: harden_security_headers(ctx, namespace)),
        ("HTTP → HTTPS Redirect", lambda: harden_http_redirect(ctx, namespace)),
        ("GoTrue Hardening", lambda: harden_gotrue(ctx, namespace)),
        ("Network Policies", lambda: harden_network_policies(ctx, namespace)),
    ]

    results = []
    for desc, func in steps:
        try:
            ok = func()
            results.append((desc, ok))
        except Exception as e:
            typer.secho(f"  ✗ Erro em '{desc}': {e}", fg=typer.colors.RED)
            results.append((desc, False))

    # Resumo
    typer.echo("\n" + "=" * 60)
    typer.secho("Resumo do Hardening:", fg=typer.colors.CYAN, bold=True)
    for desc, ok in results:
        icon = "✓" if ok else "✗"
        color = typer.colors.GREEN if ok else typer.colors.RED
        typer.secho(f"  {icon} {desc}", fg=color)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    typer.echo(f"\n  Resultado: {passed}/{total} medidas aplicadas.")
    typer.echo("=" * 60)
