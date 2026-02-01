"""Configuração de DNS interno para domínios privados (*.asgard.internal)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import typer

from raijin_server.utils import (
    ExecutionContext,
    kubectl_apply,
    logger,
    require_root,
    run_cmd,
    write_file,
)

NAMESPACE = "kube-system"
MANIFEST_PATH = Path("/tmp/raijin-internal-dns.yaml")
INGRESS_MANIFEST_PATH = Path("/tmp/raijin-internal-ingress.yaml")


def _get_node_ip(ctx: ExecutionContext) -> str:
    """Obtém o IP do nó do cluster."""
    result = run_cmd(
        [
            "kubectl",
            "get",
            "nodes",
            "-o",
            "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}",
        ],
        ctx,
        check=False,
    )
    
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    
    return "10.8.0.1"  # Fallback para IP da VPN


def _get_current_corefile(ctx: ExecutionContext) -> str:
    """Obtém o Corefile atual do CoreDNS."""
    result = run_cmd(
        [
            "kubectl", "get", "configmap", "coredns", "-n", NAMESPACE,
            "-o", "jsonpath={.data.Corefile}",
        ],
        ctx,
        check=False,
    )
    
    if result.returncode == 0:
        return result.stdout.strip()
    
    return ""


def _build_coredns_patch(domain: str, node_ip: str, current_corefile: str) -> str:
    """Cria patch para adicionar zona customizada ao Corefile existente."""
    # Bloco de configuração para o domínio interno
    internal_zone = f"""
{domain}:53 {{
    errors
    cache 30
    hosts {{
        {node_ip} grafana.{domain}
        {node_ip} prometheus.{domain}
        {node_ip} alertmanager.{domain}
        {node_ip} loki.{domain}
        {node_ip} minio.{domain}
        {node_ip} traefik.{domain}
        {node_ip} kong.{domain}
        fallthrough
    }}
}}
"""
    
    # Se já tem configuração para o domínio, não adiciona duplicado
    if f"{domain}:53" in current_corefile:
        return ""
    
    # Adiciona a nova zona no início do Corefile
    new_corefile = internal_zone + "\n" + current_corefile
    
    return new_corefile


def _build_coredns_configmap(domain: str, node_ip: str, current_corefile: str) -> str:
    """Cria ConfigMap do CoreDNS atualizado com zona customizada."""
    new_corefile = _build_coredns_patch(domain, node_ip, current_corefile)
    
    if not new_corefile:
        return ""
    
    # Escapa caracteres especiais para JSON
    escaped_corefile = new_corefile.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    
    return textwrap.dedent(
        f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: {NAMESPACE}
data:
  Corefile: |
{textwrap.indent(new_corefile, '    ')}
"""
    ).strip()


def _build_internal_ingress(domain: str, services: list[dict]) -> str:
    """Cria Ingress interno para os serviços administrativos."""
    ingress_rules = []
    
    for svc in services:
        name = svc["name"]
        namespace = svc["namespace"]
        port = svc["port"]
        host = svc["host"]
        
        ingress_rules.append(
            textwrap.dedent(
                f"""
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}-internal
  namespace: {namespace}
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
    traefik.ingress.kubernetes.io/router.priority: "10"
spec:
  ingressClassName: traefik
  rules:
    - host: {host}.{domain}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {name}
                port:
                  number: {port}
"""
            ).strip()
        )
    
    return "\n".join(ingress_rules)


def _detect_services(ctx: ExecutionContext) -> list[dict]:
    """Detecta serviços instalados que podem ter Ingress interno."""
    services = [
        {
            "name": "grafana",
            "namespace": "observability",
            "port": 80,
            "host": "grafana",
            "label": "Grafana"
        },
        {
            "name": "kube-prometheus-stack-prometheus",
            "namespace": "observability",
            "port": 9090,
            "host": "prometheus",
            "label": "Prometheus"
        },
        {
            "name": "kube-prometheus-stack-alertmanager",
            "namespace": "observability",
            "port": 9093,
            "host": "alertmanager",
            "label": "Alertmanager"
        },
        {
            "name": "loki",
            "namespace": "observability",
            "port": 3100,
            "host": "loki",
            "label": "Loki"
        },
        {
            "name": "minio-console",
            "namespace": "minio",
            "port": 9001,
            "host": "minio",
            "label": "MinIO Console"
        },
        {
            "name": "traefik",
            "namespace": "traefik",
            "port": 9000,
            "host": "traefik",
            "label": "Traefik Dashboard"
        },
        {
            "name": "kong-admin",
            "namespace": "kong",
            "port": 8001,
            "host": "kong",
            "label": "Kong Admin API"
        },
    ]
    
    available = []
    for svc in services:
        result = run_cmd(
            ["kubectl", "get", "svc", svc["name"], "-n", svc["namespace"]],
            ctx,
            check=False,
        )
        if result.returncode == 0:
            available.append(svc)
    
    return available


def _update_vpn_dns(domain: str, node_ip: str, ctx: ExecutionContext) -> None:
    """Atualiza configuração do WireGuard para usar DNS interno."""
    wg_conf = Path("/etc/wireguard/wg0.conf")
    
    if not wg_conf.exists():
        typer.secho(
            "⚠ Arquivo /etc/wireguard/wg0.conf não encontrado.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Configure a VPN primeiro com: sudo raijin vpn")
        return
    
    if ctx.dry_run:
        typer.echo(f"[dry-run] Atualizaria DNS no WireGuard para {node_ip}")
        return
    
    content = wg_conf.read_text()
    
    # Procura pela linha DNS na seção [Interface]
    lines = content.split("\n")
    updated = False
    
    for i, line in enumerate(lines):
        if line.strip().startswith("DNS ="):
            # Atualiza para usar o DNS do cluster
            lines[i] = f"DNS = {node_ip}"
            updated = True
            break
    
    if updated:
        wg_conf.write_text("\n".join(lines))
        logger.info("DNS do WireGuard atualizado para %s", node_ip)
        
        # Atualiza clientes existentes
        clients_dir = Path("/etc/wireguard/clients")
        if clients_dir.exists():
            for client_conf in clients_dir.glob("*.conf"):
                client_content = client_conf.read_text()
                client_lines = client_content.split("\n")
                
                for i, line in enumerate(client_lines):
                    if line.strip().startswith("DNS ="):
                        client_lines[i] = f"DNS = {node_ip}"
                        break
                
                client_conf.write_text("\n".join(client_lines))
                logger.info("DNS atualizado no cliente %s", client_conf.name)


def run(ctx: ExecutionContext) -> None:
    """Configura DNS interno para domínios privados."""
    require_root(ctx)
    
    typer.secho("\n🌐 Configuração de DNS Interno", fg=typer.colors.CYAN, bold=True)
    typer.echo("\nEsta ferramenta configura DNS interno para acessar serviços via")
    typer.echo("domínios amigáveis como grafana.asgard.internal")
    
    typer.secho("\n⚠ Importante:", fg=typer.colors.YELLOW, bold=True)
    typer.echo("- Use extensões reservadas para redes privadas (.internal, .home.arpa)")
    typer.echo("- Evite TLDs reais como .io, .com, .net, etc.")
    typer.echo("- Recomendado: .internal (RFC 6762)")
    
    domain = typer.prompt(
        "\nDomínio base (sem o ponto inicial)",
        default="asgard.internal",
    )
    
    if "." not in domain:
        typer.secho("⚠ Use um domínio com extensão, ex: asgard.internal", fg=typer.colors.YELLOW)
        if not typer.confirm("Continuar mesmo assim?", default=False):
            raise typer.Exit(0)
    
    # Valida extensões não recomendadas
    if any(domain.endswith(ext) for ext in [".io", ".com", ".net", ".org", ".dev"]):
        typer.secho(
            f"⚠ Extensão '{domain.split('.')[-1]}' é um TLD real, não recomendado para uso interno!",
            fg=typer.colors.RED,
            bold=True,
        )
        typer.echo("Recomendação: use .internal, .local, ou .home.arpa")
        if not typer.confirm("Continuar mesmo assim?", default=False):
            raise typer.Exit(0)
    
    node_ip = _get_node_ip(ctx)
    typer.echo(f"\nIP do nó detectado: {node_ip}")
    
    custom_ip = typer.prompt(
        "IP para resolver os domínios (ENTER para usar o detectado)",
        default=node_ip,
    )
    
    if custom_ip != node_ip:
        node_ip = custom_ip
    
    # 1. Configura CoreDNS
    typer.secho("\n1️⃣ Configurando CoreDNS...", fg=typer.colors.CYAN)
    
    # Obtém Corefile atual
    current_corefile = _get_current_corefile(ctx)
    
    if not current_corefile:
        typer.secho(
            "⚠ Não foi possível obter o Corefile atual do CoreDNS.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Verifique se o cluster está acessível.")
        raise typer.Exit(1)
    
    # Verifica se já está configurado
    if f"{domain}:53" in current_corefile:
        typer.secho(
            f"✓ Domínio {domain} já está configurado no CoreDNS.",
            fg=typer.colors.GREEN,
        )
        typer.echo("Pulando configuração do CoreDNS...")
    else:
        coredns_cm = _build_coredns_configmap(domain, node_ip, current_corefile)
        
        if not coredns_cm:
            typer.secho("⚠ Não foi possível gerar a configuração do CoreDNS.", fg=typer.colors.YELLOW)
            raise typer.Exit(1)
        
        # Mostra preview antes de aplicar
        if not ctx.dry_run:
            typer.secho("\n📄 Preview da nova configuração do CoreDNS:", fg=typer.colors.YELLOW)
            typer.echo("─" * 60)
            # Mostra apenas a zona adicionada (não o Corefile inteiro)
            typer.echo(f"Nova zona para {domain}:")
            typer.echo(f"  - grafana.{domain} → {node_ip}")
            typer.echo(f"  - prometheus.{domain} → {node_ip}")
            typer.echo(f"  - alertmanager.{domain} → {node_ip}")
            typer.echo(f"  - loki.{domain} → {node_ip}")
            typer.echo(f"  - minio.{domain} → {node_ip}")
            typer.echo(f"  - traefik.{domain} → {node_ip}")
            typer.echo(f"  - kong.{domain} → {node_ip}")
            typer.echo("─" * 60)
            
            typer.secho("\nℹ️  Esta alteração:", fg=typer.colors.CYAN)
            typer.echo("  ✓ Adiciona zona DNS para *." + domain)
            typer.echo("  ✓ Mantém todas as configurações existentes do CoreDNS")
            typer.echo("  ✓ Resolve domínios internos para " + node_ip)
            
            if not typer.confirm("\nAplicar configuração do CoreDNS?", default=True):
                typer.secho("⏭️  Pulando configuração do CoreDNS", fg=typer.colors.YELLOW)
                raise typer.Exit(0)
        
        write_file(MANIFEST_PATH, coredns_cm, ctx)
        kubectl_apply(str(MANIFEST_PATH), ctx)
        
        # Reinicia CoreDNS
        typer.echo("Reiniciando CoreDNS...")
        run_cmd(
            ["kubectl", "rollout", "restart", "deployment/coredns", "-n", NAMESPACE],
            ctx,
        )
    
    # 2. Detecta serviços disponíveis
    typer.secho("\n2️⃣ Detectando serviços...", fg=typer.colors.CYAN)
    services = _detect_services(ctx)
    
    if not services:
        typer.secho(
            "⚠ Nenhum serviço administrativo encontrado.",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Instale Grafana, Prometheus, MinIO, etc. primeiro.")
    else:
        typer.echo(f"\nEncontrados {len(services)} serviços:")
        for svc in services:
            typer.echo(f"  ✓ {svc['label']}: {svc['host']}.{domain}")
        
        if typer.confirm("\nCriar Ingress interno para esses serviços?", default=True):
            typer.secho("\n3️⃣ Criando Ingress interno...", fg=typer.colors.CYAN)
            
            ingress_manifest = _build_internal_ingress(domain, services)
            
            # Preview dos Ingress
            if not ctx.dry_run:
                typer.secho("\n📄 Preview dos Ingress (primeiros 30 linhas):", fg=typer.colors.YELLOW)
                typer.echo("─" * 60)
                lines = ingress_manifest.split("\n")
                typer.echo("\n".join(lines[:30]))
                if len(lines) > 30:
                    typer.echo(f"... ({len(lines) - 30} linhas restantes)")
                typer.echo("─" * 60)
                
                typer.secho("\nℹ️  Esses Ingress:", fg=typer.colors.CYAN)
                typer.echo("  ✓ Têm sufixo '-internal' no nome")
                typer.echo("  ✓ Não alteram Ingress existentes")
                typer.echo("  ✓ Roteiam por hostname via Traefik")
                
                if not typer.confirm("\nAplicar Ingress internos?", default=True):
                    typer.secho("⏭️  Pulando criação de Ingress", fg=typer.colors.YELLOW)
                    return
            
            write_file(INGRESS_MANIFEST_PATH, ingress_manifest, ctx)
            kubectl_apply(str(INGRESS_MANIFEST_PATH), ctx)
    
    # 3. Atualiza VPN
    if typer.confirm("\n4️⃣ Atualizar DNS do WireGuard?", default=True):
        _update_vpn_dns(domain, node_ip, ctx)
        
        typer.secho("\n⚠ Ação necessária:", fg=typer.colors.YELLOW, bold=True)
        typer.echo("1. Reinicie o WireGuard no servidor:")
        typer.echo("   sudo wg-quick down wg0 && sudo wg-quick up wg0")
        typer.echo("\n2. Distribua novos arquivos .conf aos clientes:")
        typer.echo("   sudo ls /etc/wireguard/clients/")
        typer.echo("\n3. Clientes devem reconectar ao VPN para usar o novo DNS")
    
    typer.secho("\n✓ DNS interno configurado com sucesso!", fg=typer.colors.GREEN, bold=True)
    
    if services:
        typer.secho("\n📋 Acesso aos serviços:", fg=typer.colors.CYAN, bold=True)
        typer.echo("\nDepois de conectar à VPN, acesse:")
        for svc in services:
            typer.echo(f"  • {svc['label']}: http://{svc['host']}.{domain}")
        
        typer.secho("\n💡 Dica:", fg=typer.colors.CYAN)
        typer.echo("Você não precisa mais de port-forward!")
        typer.echo("Basta conectar à VPN e acessar diretamente os domínios.")
    
    typer.secho("\n🔍 Testar resolução DNS:", fg=typer.colors.CYAN)
    typer.echo(f"kubectl run -it --rm dns-test --image=busybox --restart=Never -- nslookup grafana.{domain}")
