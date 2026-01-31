#!/bin/bash
# Checklist de validacao pre-deploy Raijin Server
# Versao auditada com verificacoes completas

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}==========================================${NC}"
echo -e "${CYAN}  Raijin Server - Checklist Pre-Deploy${NC}"
echo -e "${CYAN}==========================================${NC}"
echo ""

# Funcao auxiliar para checks
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

FAILED=0

# 1. Verificar Python
echo "1. Verificando Python..."
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version | awk '{print $2}')
    if [[ $(echo "$PY_VERSION 3.9" | awk '{print ($1 >= $2)}') -eq 1 ]]; then
        check_pass "Python $PY_VERSION >= 3.9"
    else
        check_fail "Python $PY_VERSION < 3.9"
        FAILED=1
    fi
else
    check_fail "Python3 nao encontrado"
    FAILED=1
fi

# 2. Verificar OS
echo ""
echo "2. Verificando Sistema Operacional..."
if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "$ID" == "ubuntu" ]]; then
        VERSION_NUM=$(echo "$VERSION_ID" | cut -d. -f1)
        if [[ "$VERSION_NUM" -ge 20 ]]; then
            check_pass "Ubuntu $VERSION_ID"
        else
            check_warn "Ubuntu $VERSION_ID (recomendado >= 20.04)"
        fi
    else
        check_warn "Sistema nao e Ubuntu: $ID"
    fi
else
    check_fail "/etc/os-release nao encontrado"
    FAILED=1
fi

# 3. Verificar root/sudo
echo ""
echo "3. Verificando permissoes..."
if [[ $EUID -eq 0 ]]; then
    check_pass "Executando como root"
elif groups | grep -q sudo; then
    check_pass "Usuario no grupo sudo"
else
    check_fail "Usuario nao tem permissoes sudo"
    FAILED=1
fi

# 4. Verificar espaco em disco
echo ""
echo "4. Verificando espaco em disco..."
DISK_AVAIL=$(df / | tail -1 | awk '{print $4}')
DISK_AVAIL_GB=$((DISK_AVAIL / 1024 / 1024))
if [[ $DISK_AVAIL_GB -ge 20 ]]; then
    check_pass "Espaco disponivel: ${DISK_AVAIL_GB}GB"
else
    check_fail "Espaco insuficiente: ${DISK_AVAIL_GB}GB (minimo: 20GB)"
    FAILED=1
fi

# 5. Verificar memoria
echo ""
echo "5. Verificando memoria RAM..."
MEM_TOTAL=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_GB=$((MEM_TOTAL / 1024 / 1024))
if [[ $MEM_TOTAL_GB -ge 4 ]]; then
    check_pass "Memoria RAM: ${MEM_TOTAL_GB}GB"
else
    check_fail "Memoria insuficiente: ${MEM_TOTAL_GB}GB (minimo: 4GB)"
    FAILED=1
fi

# 6. Verificar conectividade
echo ""
echo "6. Verificando conectividade..."
if ping -c 1 8.8.8.8 &> /dev/null; then
    check_pass "Conectividade com internet OK"
else
    check_fail "Sem conectividade com internet"
    FAILED=1
fi

# 7. Verificar comandos essenciais
echo ""
echo "7. Verificando comandos essenciais..."
COMMANDS=("curl" "wget" "apt-get" "systemctl" "gpg")
for cmd in "${COMMANDS[@]}"; do
    if command -v "$cmd" &> /dev/null; then
        check_pass "$cmd instalado"
    else
        check_fail "$cmd nao encontrado"
        FAILED=1
    fi
done

# 8. Verificar instalacao raijin-server
echo ""
echo "8. Verificando instalacao raijin-server..."
if command -v raijin-server &> /dev/null; then
    RAIJIN_VERSION=$(raijin-server version)
    check_pass "$RAIJIN_VERSION instalado"
else
    check_warn "raijin-server nao instalado (instale com: pip install .)"
fi

# 9. Verificar logs
echo ""
echo "9. Verificando diretorio de logs..."
if [[ -d /var/log/raijin-server ]]; then
    check_pass "Diretorio de logs: /var/log/raijin-server"
elif [[ -f ~/.raijin-server.log ]]; then
    check_warn "Usando fallback: ~/.raijin-server.log"
else
    check_warn "Nenhum log encontrado ainda"
fi

# 10. Verificar estado
echo ""
echo "10. Verificando estado dos modulos..."
STATE_DIRS=("/var/lib/raijin-server/state" "$HOME/.local/share/raijin-server/state")
FOUND_STATE=0
for dir in "${STATE_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        MODULE_COUNT=$(find "$dir" -maxdepth 1 -name '*.done' -type f 2>/dev/null | wc -l)
        if [[ $MODULE_COUNT -gt 0 ]]; then
            check_pass "$MODULE_COUNT modulos concluidos (em $dir)"
            FOUND_STATE=1
            break
        fi
    fi
done
if [[ $FOUND_STATE -eq 0 ]]; then
    check_warn "Nenhum modulo executado ainda"
fi

# Resumo
echo ""
echo -e "${CYAN}==========================================${NC}"
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ Sistema pronto para executar raijin-server${NC}"
    echo ""
    echo "Proximos passos:"
    echo "  1. sudo raijin-server validate"
    echo "  2. sudo raijin-server"
    echo "  3. Ou: raijin-server generate-config -o production.yaml"
    exit 0
else
    echo -e "${RED}✗ Sistema NAO atende pre-requisitos${NC}"
    echo ""
    echo "Corrija os problemas acima antes de prosseguir."
    exit 1
fi
