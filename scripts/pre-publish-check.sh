#!/bin/bash
# Checklist de pré-publicação para raijin-server

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${CYAN}${BOLD}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║            Checklist Pré-Publicação Raijin                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}\n"

ERRORS=0

# 1. Verificar sintaxe Python
echo -e "${CYAN}${BOLD}1. Verificando sintaxe Python...${NC}"
echo "─────────────────────────────────────────────────────────────"

PYTHON_FILES=(
    "src/raijin_server/modules/internal_dns.py"
    "src/raijin_server/modules/vpn_client.py"
    "src/raijin_server/modules/__init__.py"
    "src/raijin_server/cli.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file - ERRO DE SINTAXE"
        ((ERRORS++))
    fi
done

# 2. Verificar imports
echo -e "\n${CYAN}${BOLD}2. Verificando imports...${NC}"
echo "─────────────────────────────────────────────────────────────"

if python3 -c "
import sys
sys.path.insert(0, 'src')
from raijin_server.modules import internal_dns, vpn_client
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Imports de novos módulos OK"
else
    echo -e "${RED}✗${NC} Erro ao importar novos módulos"
    ((ERRORS++))
fi

# 3. Verificar versão
echo -e "\n${CYAN}${BOLD}3. Verificando versão...${NC}"
echo "─────────────────────────────────────────────────────────────"

SETUP_VERSION=$(grep "^version = " setup.cfg | cut -d'=' -f2 | tr -d ' ')
INIT_VERSION=$(grep "^__version__" src/raijin_server/__init__.py | cut -d'"' -f2)

echo "setup.cfg: $SETUP_VERSION"
echo "__init__.py: $INIT_VERSION"

if [ "$SETUP_VERSION" = "$INIT_VERSION" ]; then
    echo -e "${GREEN}✓${NC} Versões sincronizadas"
else
    echo -e "${RED}✗${NC} Versões diferentes!"
    ((ERRORS++))
fi

# 4. Verificar arquivos críticos
echo -e "\n${CYAN}${BOLD}4. Verificando arquivos críticos...${NC}"
echo "─────────────────────────────────────────────────────────────"

CRITICAL_FILES=(
    "src/raijin_server/modules/internal_dns.py"
    "src/raijin_server/modules/vpn_client.py"
    "scripts/port-forward-all.sh"
    "scripts/validate-internal-dns.sh"
    "docs/INTERNAL_DNS.md"
    "docs/VISUAL_TOOLS.md"
    "docs/VPN_REMOTE_ACCESS.md"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file - NÃO ENCONTRADO"
        ((ERRORS++))
    fi
done

# 5. Verificar scripts executáveis
echo -e "\n${CYAN}${BOLD}5. Verificando permissões de scripts...${NC}"
echo "─────────────────────────────────────────────────────────────"

SCRIPTS=(
    "scripts/port-forward-all.sh"
    "scripts/validate-internal-dns.sh"
    "release.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [ -x "$script" ]; then
        echo -e "${GREEN}✓${NC} $script é executável"
    else
        echo -e "${YELLOW}⚠${NC} $script não é executável (será corrigido)"
        chmod +x "$script" 2>/dev/null || true
    fi
done

# 6. Verificar .env para publicação
echo -e "\n${CYAN}${BOLD}6. Verificando configuração de publicação...${NC}"
echo "─────────────────────────────────────────────────────────────"

if [ -f .env ]; then
    echo -e "${GREEN}✓${NC} .env encontrado"
    
    if grep -q "TWINE_API_TOKEN" .env || (grep -q "TWINE_USERNAME" .env && grep -q "TWINE_PASSWORD" .env); then
        echo -e "${GREEN}✓${NC} Credenciais PyPI configuradas"
    else
        echo -e "${RED}✗${NC} Credenciais PyPI não encontradas no .env"
        echo "   Configure TWINE_API_TOKEN ou TWINE_USERNAME/TWINE_PASSWORD"
        ((ERRORS++))
    fi
else
    echo -e "${RED}✗${NC} .env não encontrado"
    echo "   Crie .env com credenciais PyPI"
    ((ERRORS++))
fi

# 7. Listar novos recursos
echo -e "\n${CYAN}${BOLD}7. Novos recursos nesta versão:${NC}"
echo "─────────────────────────────────────────────────────────────"
echo "  • Módulo internal_dns - DNS interno (*.asgard.internal)"
echo "  • Módulo vpn_client - Gerenciamento de clientes VPN"
echo "  • Script port-forward-all.sh - Port-forward automatizado"
echo "  • Script validate-internal-dns.sh - Validação pré-instalação"
echo "  • Documentação INTERNAL_DNS.md"
echo "  • Documentação VISUAL_TOOLS.md"
echo "  • Melhorias em VPN_REMOTE_ACCESS.md"

# 8. Resumo final
echo -e "\n${CYAN}${BOLD}8. Resumo${NC}"
echo "─────────────────────────────────────────────────────────────"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ PRONTO PARA PUBLICAÇÃO!${NC}\n"
    
    echo "Próximos passos:"
    echo ""
    echo "1. Definir nova versão (atual: $SETUP_VERSION):"
    echo -e "   ${CYAN}export NEW_VERSION=\"0.2.42\"${NC}"
    echo ""
    echo "2. Publicar:"
    echo -e "   ${CYAN}./release.sh \$NEW_VERSION${NC}"
    echo ""
    echo "3. No servidor de produção:"
    echo -e "   ${CYAN}sudo pip install --upgrade raijin-server${NC}"
    echo ""
    echo "4. Validar instalação:"
    echo -e "   ${CYAN}raijin --version${NC}"
    echo -e "   ${CYAN}raijin  # Verificar se novos módulos aparecem${NC}"
    echo ""
    echo "5. Testar novos módulos:"
    echo -e "   ${CYAN}# Validação pré-instalação do DNS interno${NC}"
    echo -e "   ${CYAN}sudo ~/github/raijin-server/scripts/validate-internal-dns.sh${NC}"
    echo ""
    echo -e "   ${CYAN}# Gerenciar clientes VPN${NC}"
    echo -e "   ${CYAN}sudo raijin vpn-client${NC}"
    echo ""
    echo -e "   ${CYAN}# Configurar DNS interno${NC}"
    echo -e "   ${CYAN}sudo raijin internal-dns${NC}"
    
    exit 0
else
    echo -e "${RED}${BOLD}✗ $ERRORS ERRO(S) ENCONTRADO(S)${NC}"
    echo -e "${YELLOW}Corrija os erros antes de publicar${NC}\n"
    exit 1
fi
