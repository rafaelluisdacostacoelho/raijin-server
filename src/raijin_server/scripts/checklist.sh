#!/usr/bin/env bash
set -euo pipefail

# Checklist/smoke tests basicos para um nodo provisionado pelo raijin-server.
# Execute como root (ou sudo) em um nodo control-plane ou worker.

log() { printf "[%s] %s\n" "$(date +%H:%M:%S)" "$*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Falta comando: $1"; exit 1; }
}

log "Verificando comandos basicos"
for c in kubectl helm ufw curl jq; do require_cmd "$c"; done

log "Verificando conectividade basica"
ping -c1 1.1.1.1 >/dev/null && log "Ping OK para 1.1.1.1" || echo "Ping falhou"

log "Status de data/hora"
timedatectl status | head -n 5

log "Status fail2ban"
systemctl is-active --quiet fail2ban && echo "fail2ban ativo" || echo "fail2ban inativo"

log "Status firewall (ufw)"
ufw status numbered || true

log "Sysctl rede (hardening)"
sysctl net.ipv4.conf.all.rp_filter net.ipv4.conf.default.rp_filter net.ipv4.conf.all.accept_redirects net.ipv4.conf.default.accept_redirects net.ipv4.conf.all.send_redirects net.ipv4.ip_forward

log "Kubernetes: nodes"
kubectl get nodes -o wide || true

log "Kubernetes: pods principais"
kubectl get pods -A | head -n 40 || true

log "Calico: pods"
kubectl get pods -n kube-system -l k8s-app=calico-node -o wide || true

log "Ingress (Traefik): serviços"
kubectl get svc -n traefik || true

log "Prometheus/Grafana/Loki: pods"
kubectl get pods -n observability || true

log "Velero: backups"
velero backup get || true

log "MinIO: serviço"
kubectl get svc -n minio || true

log "Kafka: serviços"
kubectl get svc -n kafka || true

log "Teste HTTP interno (se ingress exposto)"
if kubectl get svc -n traefik traefik >/dev/null 2>&1; then
  kubectl run curltest --rm -i --restart=Never --image=curlimages/curl -- curl -s -o /dev/null -w "%{http_code}\n" http://traefik.traefik.svc.cluster.local || true
fi

log "Checklist finalizado"
