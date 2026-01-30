"""Provisiona uma landing page tema Apokolips para validar ingress."""

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent, indent

import typer

from raijin_server.utils import ExecutionContext, ensure_tool, run_cmd, write_file

NAMESPACE = "apokolips-demo"
TMP_MANIFEST = Path("/tmp/raijin-apokolips.yaml")
DEFAULT_HOST = "apokolips.raijin.local"
HTML_TEMPLATE = dedent(
    """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Apokolips Signal Check</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&family=Unica+One&display=swap" rel="stylesheet">
        <style>
            :root {
                --lava: #ff4d00;
                --ember: #ff9500;
                --ash: #2c2c34;
                --void: #050007;
                --smoke: #a0a3b1;
            }
            * {
                box-sizing: border-box;
            }
            body {
                margin: 0;
                padding: 0;
                min-height: 100vh;
                font-family: 'Space Grotesk', sans-serif;
                color: #f7f7ff;
                background: radial-gradient(circle at top, rgba(255,77,0,0.45), rgba(5,0,7,0.9)), #050007;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .atmosphere {
                position: absolute;
                inset: 0;
                background: url('https://www.transparenttextures.com/patterns/asfalt-dark.png');
                opacity: 0.35;
                mix-blend-mode: screen;
                pointer-events: none;
            }
            .container {
                width: min(960px, 90vw);
                background: linear-gradient(135deg, rgba(20,22,35,0.9), rgba(10,12,22,0.95));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 28px;
                padding: 48px;
                position: relative;
                overflow: hidden;
                box-shadow: 0 40px 120px rgba(0,0,0,0.55);
                animation: rise 1.2s ease forwards;
            }
            .container::before, .container::after {
                content: '';
                position: absolute;
                width: 320px;
                height: 320px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(255,77,0,0.45), transparent 60%);
                filter: blur(20px);
                z-index: 0;
            }
            .container::before {
                top: -120px;
                right: -60px;
            }
            .container::after {
                bottom: -140px;
                left: -80px;
                background: radial-gradient(circle, rgba(255,149,0,0.4), transparent 60%);
            }
            @keyframes rise {
                from { transform: translateY(40px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            h1 {
                font-family: 'Unica One', sans-serif;
                font-size: clamp(3rem, 5vw, 4.5rem);
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: var(--lava);
                margin: 0 0 12px;
                z-index: 1;
            }
            .subhead {
                font-size: 1.15rem;
                color: var(--smoke);
                letter-spacing: 0.05em;
                margin-bottom: 32px;
                text-transform: uppercase;
            }
            .panels {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 24px;
                z-index: 1;
            }
            .panel {
                background: rgba(12,14,24,0.85);
                border-radius: 18px;
                padding: 20px;
                border: 1px solid rgba(255,255,255,0.05);
            }
            .panel h2 {
                font-size: 0.95rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--ember);
                margin: 0 0 12px;
            }
            .status {
                display: flex;
                flex-direction: column;
                gap: 6px;
                font-size: 1rem;
                color: var(--smoke);
            }
            .status span::before {
                content: '●';
                margin-right: 8px;
                color: var(--lava);
            }
            .cta {
                margin-top: 36px;
                display: flex;
                flex-wrap: wrap;
                gap: 18px;
                z-index: 1;
            }
            a.button {
                background: linear-gradient(135deg, var(--lava), var(--ember));
                color: #050007;
                text-decoration: none;
                padding: 14px 26px;
                border-radius: 999px;
                font-weight: 600;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            a.button:hover {
                transform: translateY(-2px);
                box-shadow: 0 20px 35px rgba(255,77,0,0.25);
            }
            pre {
                background: rgba(5,0,7,0.75);
                border-radius: 16px;
                padding: 16px;
                color: var(--smoke);
                font-size: 0.95rem;
                line-height: 1.5;
                overflow-x: auto;
            }
            footer {
                margin-top: 28px;
                font-size: 0.85rem;
                letter-spacing: 0.04em;
                color: rgba(247,247,255,0.7);
            }
            @media (max-width: 640px) {
                .container {
                    padding: 32px 24px;
                }
                .cta {
                    flex-direction: column;
                }
            }
        </style>
    </head>
    <body>
        <div class="atmosphere"></div>
        <main class="container">
            <h1>Apokolips Online</h1>
            <p class="subhead">Canal de prova para ingress / load balancer</p>
            <section class="panels">
                <article class="panel">
                    <h2>Estado</h2>
                    <div class="status">
                        <span>Pods sincronizados</span>
                        <span>ConfigMap montado</span>
                        <span>Ingress publicado</span>
                    </div>
                </article>
                <article class="panel">
                    <h2>Checklist</h2>
                    <div class="status">
                        <span>DNS aponta para balanceador</span>
                        <span>TLS (opcional) emitido</span>
                        <span>Firewall libera HTTP/S</span>
                    </div>
                </article>
                <article class="panel">
                    <h2>Debug Rápido</h2>
                    <pre>kubectl -n apokolips-demo get all
kubectl -n apokolips-demo describe ingress apokolips-demo
curl -H "Host: SEU_HOST" https://LB_IP/</pre>
                </article>
            </section>
            <div class="cta">
                <a class="button" href="https://github.com/darkseid/raijin-server" target="_blank" rel="noreferrer noopener">Docs Raijin</a>
                <a class="button" href="https://status.cloudflare.com/" target="_blank" rel="noreferrer noopener">Status Externo</a>
            </div>
            <footer>
                Se esta página carregou via ingress, seu cluster respondeu à chamada de Apokolips.
            </footer>
        </main>
    </body>
    </html>
    """
)


def _resolve_host() -> str:
    env_host = os.environ.get("APOKOLIPS_HOST")
    if env_host:
        return env_host.strip()
    return typer.prompt("Host (FQDN) para o ingress", default=DEFAULT_HOST).strip()


def _resolve_tls_secret() -> str | None:
    env_secret = os.environ.get("APOKOLIPS_TLS_SECRET")
    if env_secret:
        return env_secret.strip()
    use_tls = typer.confirm("Deseja referenciar um Secret TLS existente?", default=False)
    if not use_tls:
        return None
    secret = typer.prompt("Nome do Secret TLS", default="apokolips-demo-tls")
    return secret.strip() or None


def _resolve_ip_access() -> bool:
    """Pergunta se deseja acesso via IP direto (para testes)."""
    env_ip = os.environ.get("APOKOLIPS_IP_ACCESS")
    if env_ip:
        return env_ip.strip().lower() in ("1", "true", "yes")
    return typer.confirm("Habilitar acesso via IP direto? (apenas para testes)", default=True)


def _build_manifest(host: str, tls_secret: str | None, ip_access: bool = False) -> str:
        html_block = indent(HTML_TEMPLATE.strip("\n"), " " * 4)
        tls_block = ""
        if tls_secret:
                tls_block = (
                        "  tls:\n"
                        "  - hosts:\n"
                        f"    - {host}\n"
                        f"    secretName: {tls_secret}\n"
                )
        
        # Regra adicional para acesso via IP (sem host)
        ip_rule = ""
        if ip_access:
                ip_rule = """
    - http:
        paths:
        - path: /
          pathType: Prefix
          backend:
            service:
              name: apokolips-demo
              port:
                number: 80"""

        template = """\
apiVersion: v1
kind: Namespace
metadata:
    name: {namespace}
---
apiVersion: v1
kind: ConfigMap
metadata:
    name: apokolips-html
    namespace: {namespace}
data:
    index.html: |
__HTML__
---
apiVersion: apps/v1
kind: Deployment
metadata:
    name: apokolips-demo
    namespace: {namespace}
    labels:
        app: apokolips-demo
spec:
    replicas: 1
    selector:
        matchLabels:
            app: apokolips-demo
    template:
        metadata:
            labels:
                app: apokolips-demo
        spec:
            containers:
            - name: apokolips-web
                image: nginx:1.25
                ports:
                - containerPort: 80
                resources:
                    limits:
                        cpu: 100m
                        memory: 128Mi
                    requests:
                        cpu: 50m
                        memory: 64Mi
                volumeMounts:
                - name: site
                    mountPath: /usr/share/nginx/html
                    readOnly: true
            volumes:
            - name: site
                configMap:
                    name: apokolips-html
---
apiVersion: v1
kind: Service
metadata:
    name: apokolips-demo
    namespace: {namespace}
spec:
    type: ClusterIP
    selector:
        app: apokolips-demo
    ports:
    - port: 80
        targetPort: 80
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
    name: apokolips-demo
    namespace: {namespace}
    annotations:
        traefik.ingress.kubernetes.io/router.entrypoints: web,websecure
spec:
    ingressClassName: traefik
    rules:
    - host: {host}
        http:
            paths:
            - path: /
                pathType: Prefix
                backend:
                    service:
                        name: apokolips-demo
                        port:
                            number: 80__IP_RULE__
__TLS__
"""

        manifest = template.format(namespace=NAMESPACE, host=host)
        manifest = manifest.replace("__HTML__", html_block)
        manifest = manifest.replace("__IP_RULE__", ip_rule)
        manifest = manifest.replace("__TLS__", tls_block.rstrip())
        return f"{manifest.strip()}\n"


def run(ctx: ExecutionContext) -> None:
    ensure_tool("kubectl", ctx, install_hint="Instale kubectl para aplicar o manifesto do site.")
    host = _resolve_host()
    tls_secret = _resolve_tls_secret()
    ip_access = _resolve_ip_access()
    manifest = _build_manifest(host, tls_secret, ip_access)

    typer.echo("Gerando manifesto Apokolips...")
    write_file(TMP_MANIFEST, manifest, ctx)

    try:
        run_cmd(["kubectl", "apply", "-f", str(TMP_MANIFEST)], ctx)
    finally:
        TMP_MANIFEST.unlink(missing_ok=True)

    typer.secho("\nLanding page implantada!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  • Namespace: {NAMESPACE}")
    typer.echo(f"  • Host: {host}")
    if tls_secret:
        typer.echo(f"  • Secret TLS: {tls_secret}")
    if ip_access:
        typer.secho("  • Acesso via IP: HABILITADO (apenas para testes)", fg=typer.colors.YELLOW)
    
    typer.echo("\nTestes sugeridos:")
    if ip_access:
        typer.echo("  # Acesso direto via IP (teste):")
        typer.echo("  curl http://<IP_DO_SERVIDOR>/")
        typer.echo("")
    typer.echo(f"  # Acesso via DNS (produção):")
    typer.echo(f"  curl -H 'Host: {host}' http://<IP_DO_LOAD_BALANCER>/")
    typer.echo(f"  kubectl -n {NAMESPACE} get ingress {NAMESPACE}")
    typer.echo(f"  kubectl -n {NAMESPACE} get pods")

    if ip_access:
        typer.secho("\n⚠️  Lembre-se de desabilitar o acesso via IP após configurar o DNS!", fg=typer.colors.YELLOW)
        typer.echo("   Rode novamente com APOKOLIPS_IP_ACCESS=false ou responda 'não' na pergunta.")

    typer.echo("\nPara remover:")
    typer.echo(f"  kubectl delete namespace {NAMESPACE}")
