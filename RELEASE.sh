#!/usr/bin/env bash
set -euo pipefail

# Raiz do repositório (o script fica na raiz)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ne 1 ]]; then
  echo "Uso: $(basename "$0") <nova-versao>" >&2
  exit 1
fi
NEW_VERSION="$1"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Arquivo .env nao encontrado em $ROOT" >&2
  exit 1
fi

set -a
source "$ROOT/.env"
set +a

if [[ -n "${TWINE_API_TOKEN:-}" ]]; then
  TWINE_USERNAME="__token__"
  TWINE_PASSWORD="${TWINE_API_TOKEN}"
fi

if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
  echo "Defina TWINE_USERNAME/TWINE_PASSWORD ou TWINE_API_TOKEN no .env" >&2
  exit 1
fi

python - <<'PY' "$NEW_VERSION" "$ROOT"
import re
import sys
from pathlib import Path

version = sys.argv[1]
root = Path(sys.argv[2])

cfg = root / "setup.cfg"
init_py = root / "src" / "raijin_server" / "__init__.py"

print(f"Atualizando versao para {version}...")

def bump(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text()
    new_text, n = re.subn(pattern, replacement, text, flags=re.M)
    if n == 0:
        raise SystemExit(f"Padrao nao encontrado em {path}")
    path.write_text(new_text)

bump(cfg, r'^version = .+$', f'version = {version}')
bump(init_py, r'^__version__ = ".+"$', f'__version__ = "{version}"')
print("Versao atualizada em setup.cfg e src/raijin_server/__init__.py")
PY

rm -rf "$ROOT/dist" "$ROOT/build" "$ROOT/raijin_server.egg-info"

# Git commit + tag + push (antes do build para nao incluir dist/)
if command -v git >/dev/null 2>&1; then
  BRANCH="$(cd "$ROOT" && git rev-parse --abbrev-ref HEAD)"
  cd "$ROOT"
  git add setup.cfg src/raijin_server/__init__.py || true
  if git diff --cached --quiet; then
    echo "Nada para commitar"
  else
    git commit -m "Release v$NEW_VERSION"
    git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"
    git push origin "$BRANCH"
    git push origin "v$NEW_VERSION"
  fi
else
  echo "git não encontrado; pulando commit/tag/push" >&2
fi

python3 -m build
python3 -m twine upload --non-interactive dist/*

echo "Release publicado com sucesso"
