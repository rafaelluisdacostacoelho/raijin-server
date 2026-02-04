#!/usr/bin/env bash
set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Raiz do repositório (o script fica na raiz)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat << EOF
Uso: $(basename "$0") <versao> [opcoes]

Opcoes:
  -m, --message <msg>   Mensagem da release (default: "Release vX.Y.Z")
  -n, --no-push         Nao fazer push automatico
  -p, --no-pypi         Nao publicar no PyPI
  -d, --dry-run         Simular sem executar
  -h, --help            Mostrar esta ajuda

Exemplos:
  $(basename "$0") 0.3.1
  $(basename "$0") 0.3.1 -m "feat: add new module"
  $(basename "$0") 0.3.1 --dry-run
EOF
  exit 0
}

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Defaults
NEW_VERSION=""
RELEASE_MSG=""
DO_PUSH=true
DO_PYPI=true
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      RELEASE_MSG="$2"
      shift 2
      ;;
    -n|--no-push)
      DO_PUSH=false
      shift
      ;;
    -p|--no-pypi)
      DO_PYPI=false
      shift
      ;;
    -d|--dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    -*)
      log_error "Opcao desconhecida: $1"
      usage
      ;;
    *)
      if [[ -z "$NEW_VERSION" ]]; then
        NEW_VERSION="$1"
      else
        log_error "Versao ja especificada: $NEW_VERSION"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$NEW_VERSION" ]]; then
  log_error "Versao nao especificada"
  usage
fi

# Validar formato da versao (SemVer)
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  log_error "Versao invalida: $NEW_VERSION (use formato SemVer: X.Y.Z)"
  exit 1
fi

TAG_NAME="v$NEW_VERSION"
RELEASE_MSG="${RELEASE_MSG:-Release $TAG_NAME}"

# Verificar se tag ja existe
if git tag -l | grep -q "^${TAG_NAME}$"; then
  log_error "Tag $TAG_NAME ja existe!"
  log_info "Tags existentes:"
  git tag -l | sort -V | tail -5
  exit 1
fi

# Verificar working tree limpa
if [[ -n "$(git status --porcelain)" ]]; then
  log_warn "Existem alteracoes nao commitadas:"
  git status --short
  echo ""
  read -p "Deseja commitar todas as alteracoes? [y/N] " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    git add -A
    git commit -m "chore: prepare release $TAG_NAME"
    log_ok "Alteracoes commitadas"
  else
    log_error "Faca commit das alteracoes antes de criar release"
    exit 1
  fi
fi

log_info "================================================"
log_info "         RAIJIN SERVER - RELEASE"
log_info "================================================"
log_info "Versao:    $NEW_VERSION"
log_info "Tag:       $TAG_NAME"
log_info "Mensagem:  $RELEASE_MSG"
log_info "Push:      $DO_PUSH"
log_info "PyPI:      $DO_PYPI"
log_info "Dry-run:   $DRY_RUN"
log_info "================================================"
echo ""

if $DRY_RUN; then
  log_warn "MODO DRY-RUN - Nenhuma alteracao sera feita"
  echo ""
fi

# Verificar credenciais do PyPI (se necessario)
if $DO_PYPI && ! $DRY_RUN; then
  # Twine usa automaticamente ~/.pypirc ou variaveis de ambiente TWINE_USERNAME/TWINE_PASSWORD
  # Verificar se pelo menos um dos metodos esta configurado
  if [[ ! -f "$HOME/.pypirc" ]] && [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
    log_error "Credenciais PyPI nao encontradas!"
    log_info "Configure um dos seguintes:"
    log_info "  1. Crie ~/.pypirc com suas credenciais (recomendado)"
    log_info "  2. Defina TWINE_USERNAME e TWINE_PASSWORD como variaveis de ambiente"
    log_info ""
    log_info "Exemplo ~/.pypirc:"
    log_info "  [pypi]"
    log_info "  username = __token__"
    log_info "  password = pypi-XXXXXXXXXXXXXXXXXXXXXXXX"
    exit 1
  fi
fi

# 1. Atualizar versao nos arquivos
log_info "Atualizando versao nos arquivos..."

if ! $DRY_RUN; then
  python3 - <<PY "$NEW_VERSION" "$ROOT"
import re
import sys
from pathlib import Path

version = sys.argv[1]
root = Path(sys.argv[2])

cfg = root / "setup.cfg"
init_py = root / "src" / "raijin_server" / "__init__.py"

def bump(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text()
    new_text, n = re.subn(pattern, replacement, text, flags=re.M)
    if n == 0:
        raise SystemExit(f"Padrao nao encontrado em {path}")
    path.write_text(new_text)

bump(cfg, r'^version = .+$', f'version = {version}')
bump(init_py, r'^__version__ = ".+"$', f'__version__ = "{version}"')
PY
  log_ok "Versao atualizada em setup.cfg e __init__.py"
else
  log_info "[DRY-RUN] Atualizaria setup.cfg e __init__.py para $NEW_VERSION"
fi

# 2. Commit da versao
log_info "Commitando alteracao de versao..."

if ! $DRY_RUN; then
  git add setup.cfg src/raijin_server/__init__.py
  git commit -m "chore: bump version to $NEW_VERSION" || true
  log_ok "Commit criado"
else
  log_info "[DRY-RUN] Criaria commit: chore: bump version to $NEW_VERSION"
fi

# 3. Criar tag anotada
log_info "Criando tag $TAG_NAME..."

if ! $DRY_RUN; then
  git tag -a "$TAG_NAME" -m "$RELEASE_MSG"
  log_ok "Tag $TAG_NAME criada"
else
  log_info "[DRY-RUN] Criaria tag: $TAG_NAME"
fi

# 4. Push (commits + tags)
if $DO_PUSH; then
  log_info "Enviando para GitHub..."
  
  if ! $DRY_RUN; then
    git push origin master --tags
    log_ok "Push concluido (commits + tags)"
  else
    log_info "[DRY-RUN] Faria push para origin master --tags"
  fi
fi

# 5. Build e publicar no PyPI
if $DO_PYPI; then
  log_info "Construindo pacote..."
  
  if ! $DRY_RUN; then
    rm -rf "$ROOT/dist" "$ROOT/build" "$ROOT/raijin_server.egg-info"
    python3 -m build
    log_ok "Pacote construido"
    
    log_info "Publicando no PyPI..."
    python3 -m twine upload --non-interactive dist/*
    log_ok "Publicado no PyPI"
  else
    log_info "[DRY-RUN] Construiria e publicaria pacote no PyPI"
  fi
fi

# 6. Criar GitHub Release (se gh CLI disponivel)
if command -v gh &> /dev/null && $DO_PUSH; then
  log_info "Criando GitHub Release..."
  
  if ! $DRY_RUN; then
    # Gerar notas de release automaticamente baseado nos commits
    PREV_TAG=$(git tag -l | sort -V | grep -B1 "^${TAG_NAME}$" | head -1)
    
    if [[ -n "$PREV_TAG" && "$PREV_TAG" != "$TAG_NAME" ]]; then
      RELEASE_NOTES=$(git log --pretty=format:"- %s" "${PREV_TAG}..${TAG_NAME}" | head -20)
    else
      RELEASE_NOTES="Release inicial $TAG_NAME"
    fi
    
    gh release create "$TAG_NAME" \
      --title "$TAG_NAME" \
      --notes "$RELEASE_NOTES" \
      dist/*.tar.gz dist/*.whl 2>/dev/null || {
        log_warn "Nao foi possivel criar GitHub Release (gh cli nao autenticado?)"
        log_info "Crie manualmente em: https://github.com/rafaelluisdacostacoelho/raijin-server/releases/new"
      }
    
    log_ok "GitHub Release criado"
  else
    log_info "[DRY-RUN] Criaria GitHub Release com assets"
  fi
else
  if $DO_PUSH && ! $DRY_RUN; then
    log_warn "GitHub CLI (gh) nao encontrado - Release nao criado automaticamente"
    log_info "Instale com: sudo apt install gh && gh auth login"
    log_info "Ou crie manualmente: https://github.com/rafaelluisdacostacoelho/raijin-server/releases/new"
  fi
fi

echo ""
log_info "================================================"
log_ok "         RELEASE $TAG_NAME CONCLUIDO!"
log_info "================================================"
echo ""
log_info "Proximos passos:"
log_info "  1. Verificar PyPI: pip install raijin-server==$NEW_VERSION"
log_info "  2. Verificar tags: https://github.com/rafaelluisdacostacoelho/raijin-server/tags"
log_info "  3. Testar instalacao em ambiente limpo"
echo ""

