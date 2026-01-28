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
    "observability_ingress",
    "observability_dashboards",
    "full_install",
]

from raijin_server.modules import calico, essentials, firewall, grafana, harness, hardening, istio
from raijin_server.modules import kafka, kong, kubernetes, loki, minio, network, observability_dashboards
from raijin_server.modules import observability_ingress, prometheus, traefik, velero
from raijin_server.modules import bootstrap, full_install, sanitize, ssh_hardening, vpn
