# Scripts Utilitários - Raijin Server

Este diretório documenta os scripts auxiliares inclusos no pacote em `src/raijin_server/scripts/`.
Eles são instalados junto com o CLI, então você pode chamá-los mesmo fora do repositório.

## Recuperar caminho em runtime

```bash
python - <<'PY'
from raijin_server.utils import resolve_script_path
print(resolve_script_path('pre-deploy-check.sh'))
PY
```

Use o caminho retornado para executar o shell desejado ou para referenciá-lo a partir de módulos Python.

## Scripts Disponíveis

### 📦 install.sh
**Instalação rápida do CLI**

```bash
bash src/raijin_server/scripts/install.sh
```

Opções:
1. Global (sudo, todos os usuários)
2. Virtual env (recomendado para dev)
3. User install (apenas usuário atual)

---

### ✅ pre-deploy-check.sh
**Checklist de pré-requisitos antes do deploy**

```bash
bash src/raijin_server/scripts/pre-deploy-check.sh
```

Valida:
- ✓ Python >= 3.9
- ✓ Ubuntu 20.04+
- ✓ Permissões root/sudo
- ✓ Espaço em disco >= 20GB
- ✓ Memória RAM >= 4GB
- ✓ Conectividade internet
- ✓ Comandos essenciais
- ✓ Instalação raijin-server
- ✓ Diretórios de logs
- ✓ Estado dos módulos

---

### 🔍 checklist.sh
**Smoke tests para servidor provisionado**

```bash
sudo bash src/raijin_server/scripts/checklist.sh
```

Verifica:
- Comandos básicos (kubectl, helm, ufw)
- Conectividade
- Data/hora (timedatectl)
- fail2ban
- UFW
- Sysctl hardening
- Nodes Kubernetes
- Pods principais
- Calico
- Ingress
- Observabilidade
- Backups
- MinIO

---

## Uso Rápido

```bash
# 1. Instalar
bash src/raijin_server/scripts/install.sh

# 2. Validar pré-requisitos
bash src/raijin_server/scripts/pre-deploy-check.sh

# 3. Executar deploy
sudo raijin-server

# 4. Verificar instalação
sudo bash src/raijin_server/scripts/checklist.sh
```

---

## Criar Novos Scripts

Para adicionar novos scripts auxiliares:

1. Criar arquivo em `src/raijin_server/scripts/`
2. Adicionar shebang: `#!/bin/bash`
3. Tornar executável: `chmod +x src/raijin_server/scripts/seu-script.sh`
4. Documentar neste README

**Exemplo:**

```bash
#!/bin/bash
# Descrição do script

set -euo pipefail

# Seu código aqui
```

---

## Variáveis de Ambiente

Os scripts respeitam as seguintes variáveis:

- `RAIJIN_STATE_DIR` - Diretório de estado
- `RAIJIN_LOG_LEVEL` - Nível de log
- `NO_COLOR` - Desabilita cores

**Exemplo:**
```bash
export RAIJIN_STATE_DIR="$HOME/.raijin"
SCRIPT=$(python - <<'PY'
from raijin_server.utils import resolve_script_path
print(resolve_script_path('pre-deploy-check.sh'))
PY
)
bash "$SCRIPT"
```

---

## Troubleshooting

### Script não encontrado
```bash
# Verificar se está no diretório correto
ls src/raijin_server/scripts/*.sh

# Tornar executável
chmod +x src/raijin_server/scripts/*.sh
```

### Permissão negada
```bash
# Executar com sudo se necessário
sudo bash src/raijin_server/scripts/checklist.sh
```

### Erro de sintaxe
```bash
# Verificar quebras de linha (LF vs CRLF)
dos2unix src/raijin_server/scripts/*.sh
```

---

## Contribuindo

Ao adicionar scripts:
1. Use `set -euo pipefail` para robustez
2. Adicione comentários explicativos
3. Valide erros apropriadamente
4. Documente no README
5. Teste em Ubuntu 20.04+

---

**Mais informações:** [README.md](../README.md)
