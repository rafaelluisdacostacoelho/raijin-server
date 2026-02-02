"""Colecao de modulos suportados pelo CLI."""

__all__ = [
    "sanitize",
    "hardening",
    "network",
    "essentials",
    "firewall",
    "kubernetes",
    "calico",
    "istio",
    "traefik",
    "kong",
    "minio",
    "prometheus",
    "grafana",
    "loki",
    "harness",
    "velero",
    "kafka",
    "bootstrap",
    "ssh_hardening",
    "vpn",
    "vpn_client",
    "internal_dns",
    "apokolips_demo",
    "cert_manager",
    "secrets",
    "full_install",
]

from raijin_server.modules import calico, essentials, firewall, grafana, harness, hardening, istio
from raijin_server.modules import kafka, kong, kubernetes, loki, minio, network
from raijin_server.modules import prometheus, traefik, velero, apokolips_demo, secrets, cert_manager
from raijin_server.modules import bootstrap, full_install, sanitize, ssh_hardening, vpn, vpn_client, internal_dns
