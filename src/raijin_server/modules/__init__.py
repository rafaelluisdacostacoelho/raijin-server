"""Colecao de modulos suportados pelo CLI."""

__all__ = [
    "sanitize",
    "hardening",
    "network",
    "network_config",
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
    "ssh_manager",
    "vpn",
    "vpn_client",
    "vpn_manager",
    "internal_dns",
    "cert_manager",
    "secrets",
    "full_install",
    "supabase",
    "supabase_security",
    "gitops",
]

from raijin_server.modules import argo, calico, essentials, firewall, grafana, harbor, hardening, istio
from raijin_server.modules import kong, kubernetes, landing, loki, minio, network, network_config
from raijin_server.modules import prometheus, traefik, velero, secrets, cert_manager
from raijin_server.modules import bootstrap, full_install, sanitize, ssh_hardening, ssh_manager
from raijin_server.modules import vpn, vpn_client, vpn_manager, internal_dns, supabase, supabase_security, gitops
