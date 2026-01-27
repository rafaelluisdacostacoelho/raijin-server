"""Colecao de modulos suportados pelo CLI."""

__all__ = [
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
]

from raijin_server.modules import calico, essentials, firewall, grafana, harness, hardening, istio
from raijin_server.modules import kafka, kong, kubernetes, loki, minio, network, prometheus, traefik
from raijin_server.modules import velero
