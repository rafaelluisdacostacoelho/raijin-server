"""Provisiona ingressos seguros para Grafana, Prometheus e Alertmanager."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Dict, List

import typer

from raijin_server.utils import (
    ExecutionContext,
    kubectl_apply,
    kubectl_create_ns,
    require_root,
    write_file,
)

MANIFEST_PATH = Path("/tmp/raijin-observability-ingress.yaml")

COMPONENTS: List[Dict[str, object]] = [
    {
        "key": "grafana",
        "label": "Grafana",
        "service": "grafana",
        "port": 80,
        "default_host": "grafana.example.com",
        "default_tls": "grafana-tls",
        "auth_secret": "grafana-basic-auth",
        "middleware": "grafana-auth",
    },
    {
        "key": "prometheus",
        "label": "Prometheus",
        "service": "kube-prometheus-stack-prometheus",
        "port": 9090,
        "default_host": "prometheus.example.com",
        "default_tls": "prometheus-tls",
        "auth_secret": "prometheus-basic-auth",
        "middleware": "prometheus-auth",
    },
    {
        "key": "alertmanager",
        "label": "Alertmanager",
        "service": "kube-prometheus-stack-alertmanager",
        "port": 9093,
        "default_host": "alerts.example.com",
        "default_tls": "alertmanager-tls",
        "auth_secret": "alertmanager-basic-auth",
        "middleware": "alertmanager-auth",
    },
]


def _generate_htpasswd(username: str, password: str) -> str:
  try:
    result = subprocess.run(
      ["openssl", "passwd", "-6", password],
      capture_output=True,
      text=True,
      check=True,
    )
    hashed = result.stdout.strip()
  except Exception:
    import crypt

    hashed = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
  return f"{username}:{hashed}"


def _build_manifest(
    namespace: str,
    ingress_class: str,
    services: List[Dict[str, object]],
    encoded_users: str,
    issuer_name: str,
    issuer_kind: str,
) -> str:
    documents: List[str] = []

    for svc in services:
        host = svc["host"]
        tls_secret = svc["tls_secret"]
        auth_secret = svc["auth_secret"]
        middleware = svc["middleware"]
        service_name = svc["service"]
        port = svc["port"]
        name = svc["key"]

        documents.append(
            f"""apiVersion: v1
kind: Secret
metadata:
  name: {auth_secret}
  namespace: {namespace}
type: Opaque
data:
  users: {encoded_users}
"""
        )

        documents.append(
            f"""apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: {middleware}
  namespace: {namespace}
spec:
  basicAuth:
    secret: {auth_secret}
    removeHeader: true
"""
        )

        if issuer_name:
            documents.append(
                f"""apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: {name}-ingress-cert
  namespace: {namespace}
spec:
  secretName: {tls_secret}
  dnsNames:
    - {host}
  issuerRef:
    name: {issuer_name}
    kind: {issuer_kind}
"""
            )

        documents.append(
            f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}-secure
  namespace: {namespace}
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: {namespace}-{middleware}@kubernetescrd
spec:
  ingressClassName: {ingress_class}
  rules:
    - host: {host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {service_name}
                port:
                  number: {port}
  tls:
    - secretName: {tls_secret}
      hosts:
        - {host}
"""
        )

    return "---\n".join(documents)


def run(ctx: ExecutionContext) -> None:
    require_root(ctx)
    typer.echo("Provisionando ingress seguro para observabilidade...")

    namespace = typer.prompt("Namespace dos componentes", default="observability")
    ingress_class = typer.prompt("IngressClass dedicada", default="traefik")
    username = typer.prompt("Usuario para basic auth", default="observability")
    password = typer.prompt(
        "Senha para basic auth",
        hide_input=True,
        confirmation_prompt=True,
    )

    configured: List[Dict[str, object]] = []
    for comp in COMPONENTS:
        host = typer.prompt(f"Host para {comp['label']}", default=comp["default_host"])
        tls_secret = typer.prompt(
            f"Secret TLS para {comp['label']}",
            default=comp["default_tls"],
        )
        configured.append({**comp, "host": host, "tls_secret": tls_secret})

    issue_certs = typer.confirm("Gerar Certificates via cert-manager?", default=True)
    issuer_name = ""
    issuer_kind = "ClusterIssuer"
    if issue_certs:
        issuer_name = typer.prompt("Nome do issuer (cert-manager)", default="letsencrypt-prod")
        issuer_kind = typer.prompt("Tipo do issuer (Issuer/ClusterIssuer)", default="ClusterIssuer")

    secret_line = _generate_htpasswd(username, password)
    encoded_users = base64.b64encode(secret_line.encode()).decode()

    kubectl_create_ns(namespace, ctx)

    manifest = _build_manifest(
        namespace,
        ingress_class,
        configured,
        encoded_users,
        issuer_name,
        issuer_kind,
    )

    write_file(MANIFEST_PATH, manifest, ctx)
    kubectl_apply(str(MANIFEST_PATH), ctx)

    typer.secho("Ingress seguro aplicado com sucesso.", fg=typer.colors.GREEN)
    typer.echo("Hosts publicados:")
    for svc in configured:
        typer.echo(f"  - {svc['label']}: https://{svc['host']}")
    if not issuer_name:
        typer.secho(
            "Certificados nao foram criados automaticamente. Certifique-se de que os secrets TLS existem.",
            fg=typer.colors.YELLOW,
        )
