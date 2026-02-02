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
    "harbor",
    "argo",
    "velero",
    "landing",
    "bootstrap",
    "ssh_hardening",
    "vpn",
    "vpn_client",
    "internal_dns",
    "cert_manager",
    "secrets",
    "full_install",
]

from raijin_server.modules import argo, calico, essentials, firewall, grafana, harbor, hardening, istio
from raijin_server.modules import kong, kubernetes, landing, loki, minio, network
from raijin_server.modules import prometheus, traefik, velero, secrets, cert_manager
from raijin_server.modules import bootstrap, full_install, sanitize, ssh_hardening, vpn, vpn_client, internal_dns
