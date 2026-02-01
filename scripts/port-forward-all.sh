#!/bin/bash
# Script para iniciar todos os port-forwards necessários para dashboards administrativos
# Uso: ./port-forward-all.sh [start|stop|status|restart]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="/tmp/raijin-port-forward-pids"
LOG_DIR="/tmp/raijin-port-forward-logs"

# Configuração dos port-forwards
# Formato: "namespace:service:local_port:remote_port:name"
FORWARDS=(
    "observability:grafana:3000:80:Grafana"
    "observability:kube-prometheus-stack-prometheus:9090:9090:Prometheus"
    "observability:kube-prometheus-stack-alertmanager:9093:9093:Alertmanager"
    "minio:minio-console:9001:9001:MinIO Console"
    "traefik:deployment/traefik:9000:9000:Traefik Dashboard"
    "kong:kong-kong-admin:8001:8001:Kong Admin API"
    "observability:loki:3100:3100:Loki"
)

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Funções auxiliares
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Verifica se kubectl está configurado
check_kubectl() {
    if ! kubectl cluster-info &>/dev/null; then
        log_error "kubectl não está configurado ou cluster não está acessível"
        log_info "Certifique-se de estar conectado à VPN e ter o kubeconfig configurado"
        exit 1
    fi
}

# Cria diretórios necessários
setup_dirs() {
    mkdir -p "$PID_DIR" "$LOG_DIR"
}

# Verifica se um serviço existe
service_exists() {
    local namespace=$1
    local resource=$2
    
    # Remove "deployment/" ou "svc/" prefix se existir
    local resource_type="svc"
    local resource_name=$resource
    
    if [[ $resource == deployment/* ]]; then
        resource_type="deployment"
        resource_name="${resource#deployment/}"
    fi
    
    kubectl -n "$namespace" get "$resource_type" "$resource_name" &>/dev/null
}

# Inicia um port-forward
start_forward() {
    local namespace=$1
    local service=$2
    local local_port=$3
    local remote_port=$4
    local name=$5
    
    local pid_file="$PID_DIR/${name// /_}.pid"
    local log_file="$LOG_DIR/${name// /_}.log"
    
    # Verifica se já está rodando
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_warning "$name já está rodando (PID: $pid)"
            return 0
        else
            rm -f "$pid_file"
        fi
    fi
    
    # Verifica se o serviço existe
    if ! service_exists "$namespace" "$service"; then
        log_warning "$name não encontrado em $namespace/$service (pode não estar instalado)"
        return 1
    fi
    
    # Verifica se a porta local está em uso
    if lsof -Pi :$local_port -sTCP:LISTEN -t &>/dev/null; then
        log_warning "Porta $local_port já está em uso, pulando $name"
        return 1
    fi
    
    # Inicia o port-forward em background
    log_info "Iniciando $name ($namespace/$service -> localhost:$local_port)..."
    kubectl -n "$namespace" port-forward "$service" "$local_port:$remote_port" \
        > "$log_file" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$pid_file"
    
    # Aguarda um momento e verifica se ainda está rodando
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        log_success "$name rodando em http://localhost:$local_port (PID: $pid)"
        return 0
    else
        log_error "$name falhou ao iniciar (veja $log_file)"
        rm -f "$pid_file"
        return 1
    fi
}

# Para um port-forward
stop_forward() {
    local name=$1
    local pid_file="$PID_DIR/${name// /_}.pid"
    
    if [[ ! -f "$pid_file" ]]; then
        log_warning "$name não está rodando"
        return 1
    fi
    
    local pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
        log_info "Parando $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 0.5
        
        # Force kill se necessário
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        
        rm -f "$pid_file"
        log_success "$name parado"
    else
        log_warning "$name não está mais rodando"
        rm -f "$pid_file"
    fi
}

# Inicia todos os port-forwards
start_all() {
    check_kubectl
    setup_dirs
    
    echo -e "${CYAN}=== Iniciando Port-Forwards ===${NC}\n"
    
    local started=0
    local failed=0
    
    for forward in "${FORWARDS[@]}"; do
        IFS=: read -r namespace service local_port remote_port name <<< "$forward"
        if start_forward "$namespace" "$service" "$local_port" "$remote_port" "$name"; then
            ((started++))
        else
            ((failed++))
        fi
    done
    
    echo ""
    echo -e "${CYAN}=== Resumo ===${NC}"
    log_success "$started port-forwards iniciados"
    [[ $failed -gt 0 ]] && log_warning "$failed port-forwards falharam ou foram pulados"
    
    echo ""
    echo -e "${BLUE}Acesse os dashboards:${NC}"
    echo "  Grafana:           http://localhost:3000"
    echo "  Prometheus:        http://localhost:9090"
    echo "  Alertmanager:      http://localhost:9093"
    echo "  MinIO Console:     http://localhost:9001"
    echo "  Traefik Dashboard: http://localhost:9000/dashboard/"
    echo "  Kong Admin API:    http://localhost:8001"
    echo "  Loki:              http://localhost:3100"
    echo ""
    echo -e "${YELLOW}Para parar todos: $0 stop${NC}"
}

# Para todos os port-forwards
stop_all() {
    setup_dirs
    
    echo -e "${CYAN}=== Parando Port-Forwards ===${NC}\n"
    
    local stopped=0
    
    for forward in "${FORWARDS[@]}"; do
        IFS=: read -r namespace service local_port remote_port name <<< "$forward"
        if stop_forward "$name"; then
            ((stopped++))
        fi
    done
    
    echo ""
    log_success "$stopped port-forwards parados"
}

# Mostra status dos port-forwards
show_status() {
    setup_dirs
    
    echo -e "${CYAN}=== Status dos Port-Forwards ===${NC}\n"
    
    local running=0
    local stopped=0
    
    for forward in "${FORWARDS[@]}"; do
        IFS=: read -r namespace service local_port remote_port name <<< "$forward"
        local pid_file="$PID_DIR/${name// /_}.pid"
        
        if [[ -f "$pid_file" ]]; then
            local pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${GREEN}✓${NC} $name (PID: $pid, Port: $local_port)"
                ((running++))
            else
                echo -e "${RED}✗${NC} $name (processo morto)"
                ((stopped++))
                rm -f "$pid_file"
            fi
        else
            echo -e "${YELLOW}○${NC} $name (não iniciado)"
            ((stopped++))
        fi
    done
    
    echo ""
    log_info "$running rodando, $stopped parados"
}

# Reinicia todos os port-forwards
restart_all() {
    stop_all
    sleep 2
    start_all
}

# Limpa processos órfãos
cleanup() {
    log_info "Limpando processos órfãos..."
    
    # Para todos os processos conhecidos
    for pid_file in "$PID_DIR"/*.pid; do
        [[ -f "$pid_file" ]] || continue
        local pid=$(cat "$pid_file" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    done
    
    # Limpa logs antigos
    rm -f "$LOG_DIR"/*.log
    
    log_success "Limpeza concluída"
}

# Menu principal
case "${1:-start}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    restart)
        restart_all
        ;;
    cleanup)
        cleanup
        ;;
    *)
        echo "Uso: $0 {start|stop|status|restart|cleanup}"
        echo ""
        echo "Comandos:"
        echo "  start    - Inicia todos os port-forwards"
        echo "  stop     - Para todos os port-forwards"
        echo "  status   - Mostra status dos port-forwards"
        echo "  restart  - Reinicia todos os port-forwards"
        echo "  cleanup  - Para todos e limpa arquivos temporários"
        exit 1
        ;;
esac
