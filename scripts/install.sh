#!/bin/bash
# Script de instalacao rapida do Raijin Server CLI
# Para Ubuntu Server 20.04+

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Raijin Server - Instalação Rápida${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 não encontrado${NC}"
    echo "Instale com: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PY_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python $PY_VERSION encontrado"

# Verificar se está no diretório do projeto
if [ ! -f "setup.cfg" ]; then
    echo -e "${RED}✗ Não está no diretório do projeto raijin-server${NC}"
    echo "Execute este script no diretório raiz do projeto"
    exit 1
fi

# Perguntar tipo de instalação
echo ""
echo "Escolha o tipo de instalação:"
echo "  1) Global (requer sudo, todos os usuários)"
echo "  2) Virtual env (recomendado para desenvolvimento)"
echo "  3) User install (apenas usuário atual)"
read -r -p "Opção [2]: " INSTALL_TYPE
INSTALL_TYPE=${INSTALL_TYPE:-2}

echo ""
case $INSTALL_TYPE in
    1)
        echo -e "${YELLOW}Instalando globalmente...${NC}"
        sudo python3 -m pip install .
        BIN_PATH=$(which raijin-server)
        ;;
    2)
        echo -e "${YELLOW}Criando virtual environment...${NC}"
        python3 -m venv .venv
        # shellcheck disable=SC1091
        source .venv/bin/activate
        pip install --upgrade pip
        pip install -e .
        BIN_PATH=".venv/bin/raijin-server"
        
        # Criar wrapper
        cat > raijin-server-run.sh << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
raijin-server "$@"
EOF
        chmod +x raijin-server-run.sh
        echo -e "${GREEN}✓${NC} Wrapper criado: ./raijin-server-run.sh"
        ;;
    3)
        echo -e "${YELLOW}Instalando para usuário atual...${NC}"
        python3 -m pip install --user .
        BIN_PATH="$HOME/.local/bin/raijin-server"
        
        # Adicionar ao PATH se necessário
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            echo "export PATH=\"$HOME/.local/bin:$PATH\"" >> ~/.bashrc
            echo -e "${YELLOW}⚠${NC} Adicionado $HOME/.local/bin ao PATH"
            echo "Execute: source ~/.bashrc"
        fi
        ;;
    *)
        echo -e "${RED}✗ Opção inválida${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✓ Instalação concluída!${NC}"
echo ""

# Testar instalação
echo "Testando instalação..."
if [ "$INSTALL_TYPE" -eq 2 ]; then
    VERSION=$($BIN_PATH version)
else
    VERSION=$(raijin-server version)
fi
echo -e "${GREEN}✓${NC} $VERSION"

# Mostrar próximos passos
echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Próximos Passos${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

case $INSTALL_TYPE in
    2)
        echo "Para usar o CLI:"
        echo "  source .venv/bin/activate"
        echo "  sudo raijin-server validate"
        echo ""
        echo "Ou use o wrapper:"
        echo "  sudo ./raijin-server-run.sh validate"
        ;;
    *)
        echo "Para validar o sistema:"
        echo "  sudo raijin-server validate"
        echo ""
        echo "Para ver o menu interativo:"
        echo "  sudo raijin-server"
        echo ""
        echo "Para gerar configuração:"
        echo "  raijin-server generate-config -o production.yaml"
        ;;
esac

echo ""
echo "Documentação:"
echo "  README.md         - Guia principal"
echo "  AUDIT.md          - Relatório de auditoria"
echo "  EXAMPLES.md       - Exemplos práticos"
echo ""
echo -e "${GREEN}Instalação bem-sucedida!${NC} 🚀"
