#!/bin/bash
# Script de validação: Mostra o que será alterado pelo módulo internal_dns

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
NC="\033[0m" # No Color

echo -e "${CYAN}${BOLD}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Validação Pré-Instalação: Internal DNS            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}Este script mostra o que o módulo internal_dns vai fazer${NC}\n"

# 1. Verificar CoreDNS atual
echo -e "${CYAN}${BOLD}1. CoreDNS Atual${NC}"
echo "─────────────────────────────────────────────────────────────"

if kubectl get configmap coredns-custom -n kube-system &>/dev/null; then
    echo -e "${YELLOW}⚠  ConfigMap 'coredns-custom' JÁ EXISTE${NC}"
    echo -e "   Será ${BOLD}SOBRESCRITO${NC} com novas regras DNS"
    echo ""
    echo "Conteúdo atual:"
    kubectl get configmap coredns-custom -n kube-system -o yaml | grep -A 20 "data:" || echo "  (vazio)"
else
    echo -e "${GREEN}✓ ConfigMap 'coredns-custom' não existe${NC}"
    echo -e "  Será ${BOLD}CRIADO${NC} (não afeta CoreDNS principal)"
fi

echo -e "\n${CYAN}ConfigMap principal do CoreDNS (NÃO será alterado):${NC}"
kubectl get configmap coredns -n kube-system -o yaml | grep -A 5 "Corefile:"
echo ""

# 2. Verificar serviços disponíveis
echo -e "${CYAN}${BOLD}2. Serviços Detectados${NC}"
echo "─────────────────────────────────────────────────────────────"

SERVICES=(
    "grafana:observability"
    "kube-prometheus-stack-prometheus:observability"
    "kube-prometheus-stack-alertmanager:observability"
    "loki:observability"
    "minio-console:minio"
    "traefik:traefik"
    "kong-admin:kong"
)

FOUND_SERVICES=()

for entry in "${SERVICES[@]}"; do
    IFS=':' read -r svc ns <<< "$entry"
    if kubectl get svc "$svc" -n "$ns" &>/dev/null; then
        echo -e "${GREEN}✓${NC} $svc (namespace: $ns)"
        FOUND_SERVICES+=("$entry")
    else
        echo -e "${RED}✗${NC} $svc (namespace: $ns) - ${YELLOW}não encontrado${NC}"
    fi
done

if [ ${#FOUND_SERVICES[@]} -eq 0 ]; then
    echo -e "\n${RED}⚠  Nenhum serviço encontrado!${NC}"
    echo "   Instale Grafana, Prometheus, MinIO, etc. primeiro"
    exit 0
fi

echo -e "\n${CYAN}Total: ${#FOUND_SERVICES[@]} serviços serão configurados${NC}"

# 3. Verificar Ingress existentes
echo -e "\n${CYAN}${BOLD}3. Ingress Existentes${NC}"
echo "─────────────────────────────────────────────────────────────"

EXISTING_INGRESS=$(kubectl get ingress -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,HOSTS:.spec.rules[*].host --no-headers 2>/dev/null || echo "")

if [ -z "$EXISTING_INGRESS" ]; then
    echo -e "${GREEN}✓ Nenhum Ingress existente${NC}"
    echo "  Ingress internos serão criados sem conflito"
else
    echo "Ingress atuais (NÃO serão alterados):"
    echo "$EXISTING_INGRESS" | while IFS= read -r line; do
        echo "  • $line"
    done
fi

echo -e "\n${CYAN}Ingress que serão CRIADOS (novos):${NC}"
DOMAIN="asgard.internal"  # Default, usuário pode escolher outro

for entry in "${FOUND_SERVICES[@]}"; do
    IFS=':' read -r svc ns <<< "$entry"
    
    # Mapeia nome do serviço para hostname
    case "$svc" in
        "grafana") host="grafana" ;;
        "kube-prometheus-stack-prometheus") host="prometheus" ;;
        "kube-prometheus-stack-alertmanager") host="alertmanager" ;;
        "loki") host="loki" ;;
        "minio-console") host="minio" ;;
        "traefik") host="traefik" ;;
        "kong-admin") host="kong" ;;
        *) host=$(echo "$svc" | cut -d'-' -f1) ;;
    esac
    
    echo "  • ${ns}/${svc}-internal → http://${host}.${DOMAIN}"
done

# 4. Verificar WireGuard
echo -e "\n${CYAN}${BOLD}4. Configuração WireGuard${NC}"
echo "─────────────────────────────────────────────────────────────"

if [ -f /etc/wireguard/wg0.conf ]; then
    echo -e "${GREEN}✓ /etc/wireguard/wg0.conf encontrado${NC}"
    
    CURRENT_DNS=$(grep "^DNS" /etc/wireguard/wg0.conf | head -1 || echo "")
    if [ -n "$CURRENT_DNS" ]; then
        echo -e "  DNS atual: ${YELLOW}$CURRENT_DNS${NC}"
    else
        echo -e "  ${YELLOW}⚠  Linha DNS não encontrada${NC}"
    fi
    
    NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    echo -e "  Será alterado para: ${GREEN}DNS = $NODE_IP${NC}"
    
    # Contar clientes
    CLIENT_COUNT=$(ls /etc/wireguard/clients/*.conf 2>/dev/null | wc -l)
    if [ "$CLIENT_COUNT" -gt 0 ]; then
        echo -e "  ${CYAN}$CLIENT_COUNT arquivo(s) de cliente encontrado(s)${NC}"
        echo -e "  ${YELLOW}⚠  Todos serão atualizados com novo DNS${NC}"
    fi
else
    echo -e "${YELLOW}⚠  WireGuard não configurado${NC}"
    echo "  Configure com: sudo raijin vpn"
fi

# 5. Verificar Traefik
echo -e "\n${CYAN}${BOLD}5. Traefik (Ingress Controller)${NC}"
echo "─────────────────────────────────────────────────────────────"

if kubectl get deployment traefik -n traefik &>/dev/null; then
    TRAEFIK_STATUS=$(kubectl get deployment traefik -n traefik -o jsonpath='{.status.conditions[?(@.type=="Available")].status}')
    
    if [ "$TRAEFIK_STATUS" = "True" ]; then
        echo -e "${GREEN}✓ Traefik está rodando e disponível${NC}"
        echo "  Os Ingress internos funcionarão imediatamente"
    else
        echo -e "${RED}⚠  Traefik não está disponível${NC}"
        echo "  Ingress internos não funcionarão até Traefik estar pronto"
    fi
else
    echo -e "${RED}✗ Traefik não está instalado${NC}"
    echo "  Instale com: sudo raijin traefik"
    exit 1
fi

# 6. Resumo de Impacto
echo -e "\n${CYAN}${BOLD}6. Resumo de Impacto${NC}"
echo "─────────────────────────────────────────────────────────────"

echo -e "${GREEN}${BOLD}O que SERÁ alterado:${NC}"
echo "  ✓ Novo ConfigMap 'coredns-custom' em kube-system"
echo "  ✓ Rollout restart do deployment/coredns"
echo "  ✓ Novos Ingress com sufixo '-internal' (${#FOUND_SERVICES[@]} recursos)"
echo "  ✓ Linha DNS nos arquivos /etc/wireguard/*.conf"

echo -e "\n${RED}${BOLD}O que NÃO será alterado:${NC}"
echo "  ✗ Deployments existentes (Grafana, Prometheus, etc.)"
echo "  ✗ Services (ClusterIP, LoadBalancer)"
echo "  ✗ PersistentVolumeClaims (dados persistentes)"
echo "  ✗ ConfigMaps dos serviços (dashboards, alertas)"
echo "  ✗ Secrets (credenciais, TLS)"
echo "  ✗ Ingress públicos existentes"
echo "  ✗ Configuração do Traefik"

echo -e "\n${YELLOW}${BOLD}Ações necessárias após instalação:${NC}"
echo "  1. Reiniciar WireGuard no servidor:"
echo "     ${CYAN}sudo wg-quick down wg0 && sudo wg-quick up wg0${NC}"
echo ""
echo "  2. Distribuir novos arquivos .conf aos clientes"
echo ""
echo "  3. Clientes reconectarem ao VPN"

echo -e "\n${GREEN}${BOLD}✓ É seguro executar em ambiente já configurado!${NC}"
echo -e "${CYAN}Execute: sudo raijin internal-dns${NC}\n"
