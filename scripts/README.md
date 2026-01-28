# Scripts Utilitários - Raijin Server

Este diretório contém scripts auxiliares para instalação, validação e manutenção do raijin-server.

## Scripts Disponíveis

### 📦 install.sh
**Instalação rápida do CLI**

```bash
bash scripts/install.sh
```

Opções:
1. Global (sudo, todos os usuários)
2. Virtual env (recomendado para dev)
3. User install (apenas usuário atual)

---

### ✅ pre-deploy-check.sh
**Checklist de pré-requisitos antes do deploy**

```bash
bash scripts/pre-deploy-check.sh
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
sudo bash scripts/checklist.sh
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
bash scripts/install.sh

# 2. Validar pré-requisitos
bash scripts/pre-deploy-check.sh

# 3. Executar deploy
sudo raijin-server

# 4. Verificar instalação
sudo bash scripts/checklist.sh
```

---

## Criar Novos Scripts

Para adicionar novos scripts auxiliares:

1. Criar arquivo em `scripts/`
2. Adicionar shebang: `#!/bin/bash`
3. Tornar executável: `chmod +x scripts/seu-script.sh`
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
bash scripts/pre-deploy-check.sh
```

---

## Troubleshooting

### Script não encontrado
```bash
# Verificar se está no diretório correto
ls scripts/*.sh

# Tornar executável
chmod +x scripts/*.sh
```

### Permissão negada
```bash
# Executar com sudo se necessário
sudo bash scripts/checklist.sh
```

### Erro de sintaxe
```bash
# Verificar quebras de linha (LF vs CRLF)
dos2unix scripts/*.sh
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
