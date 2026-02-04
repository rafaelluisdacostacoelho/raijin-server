# Raijin Server

CLI em Python para automatizar setup e hardening de servidores Ubuntu Server. Orquestra rede, firewall, Kubernetes, observabilidade e backups de forma segura e idempotente.

## Índice

- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Primeiros Passos](#primeiros-passos)
- [Módulos Disponíveis](#módulos-disponíveis)
- [Acesso Remoto Seguro](#acesso-remoto-seguro)
- [Documentação](#documentação)

---

## Requisitos

- Ubuntu Server 20.04+
- Python 3.9+
- 4GB RAM mínimo (8GB recomendado)
- 20GB disco livre

```bash
# Instalar dependências Python (se necessário)
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
```

---

## Instalação

> ⚠️ **Importante:** Sempre use um ambiente virtual (venv) para isolar dependências.

### 1. Criar ambiente virtual

```bash
# Criar venv chamado "midgard"
python3 -m venv ~/.venvs/midgard

# Ativar o venv
source ~/.venvs/midgard/bin/activate

# Atualizar pip
pip install -U pip setuptools
```

### 2. Instalar Raijin Server

```bash
# Instalar do PyPI (substitua X.X.X pela versão desejada)
pip install raijin-server==X.X.X
```

### 3. Executar com sudo

O Raijin precisa de permissões root. Use `-E` para preservar o venv:

```bash
# Verificar instalação
sudo -E ~/.venvs/midgard/bin/raijin-server --version

# Abrir menu interativo
sudo -E ~/.venvs/midgard/bin/raijin-server menu
```

### 4. Desativar venv (quando terminar)

```bash
deactivate
```

> 💡 **Dica:** Para reinstalar, remova o venv (`rm -rf ~/.venvs/midgard`) e repita os passos.

---

## Primeiros Passos

### Validar Sistema

Verifica se o sistema atende aos pré-requisitos:

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server validate
```

### Menu Interativo

Forma mais fácil de usar - navegue pelos módulos visualmente:

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server menu
```

### Instalação Completa Automatizada

Instala tudo de uma vez, na ordem correta:

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server full-install
```

**Opções úteis:**

| Opção | Descrição |
|-------|-----------|
| `--select-steps` | Escolher módulos antes de executar |
| `--confirm-each` | Confirmar cada módulo |
| `--dry-run` | Simular sem aplicar mudanças |
| `--steps "a,b,c"` | Executar módulos específicos |

### Executar Módulo Específico

```bash
# Exemplo: instalar apenas Kubernetes
sudo -E ~/.venvs/midgard/bin/raijin-server kubernetes

# Modo dry-run (apenas simula)
sudo -E ~/.venvs/midgard/bin/raijin-server --dry-run kubernetes
```

---

## Módulos Disponíveis

### 🔧 Base do Sistema

| Módulo | Descrição |
|--------|-----------|
| `sanitize` | Remove instalações antigas do Kubernetes |
| `bootstrap` | Instala helm, kubectl, containerd |
| `essentials` | Pacotes básicos (curl, git, jq, etc.) |
| `hardening` | Fail2ban, sysctl, unattended-upgrades |
| `network` | IP estático via Netplan (opcional) |
| `firewall` | Regras UFW para SSH/HTTP/HTTPS/K8s |

### ☸️ Kubernetes

| Módulo | Descrição |
|--------|-----------|
| `kubernetes` | Inicializa cluster com kubeadm |
| `calico` | CNI com network policies |
| `metallb` | LoadBalancer para bare metal |
| `secrets` | Sealed-secrets + external-secrets |
| `cert-manager` | Certificados TLS automáticos |

### 🌐 Ingress (escolha um)

| Módulo | Descrição |
|--------|-----------|
| `traefik` | Ingress controller com TLS/ACME |
| `kong` | API Gateway avançado |

### 📊 Observabilidade

| Módulo | Descrição |
|--------|-----------|
| `prometheus` | Métricas e alertas |
| `grafana` | Dashboards de visualização |
| `loki` | Agregação de logs |
| `observability-ingress` | Ingress seguro para dashboards |
| `observability-dashboards` | Dashboards pré-configurados |

### 💾 Storage e Backup

| Módulo | Descrição |
|--------|-----------|
| `minio` | Object storage S3-compatível |
| `velero` | Backup e restore do cluster |

### 🌐 Landing Page

| Módulo | Descrição |
|--------|-----------|
| `landing` | Landing page de teste para verificar acesso público |

### 🔒 VPN e Segurança

| Módulo | Descrição |
|--------|-----------|
| `vpn` | Servidor WireGuard + cliente inicial |
| `vpn-client` | Gerenciar clientes VPN (adicionar/remover) |
| `ssh-hardening` | Políticas seguras de SSH |
| `internal-dns` | DNS interno (*.asgard.internal) |

### 🚀 Service Mesh

| Módulo | Descrição |
|--------|-----------|
| `istio` | Service mesh completo |

---

## Acesso Remoto Seguro

O Raijin prioriza segurança. Dashboards administrativos **não são expostos publicamente** por padrão.

### Opção 1: VPN (Recomendado)

```bash
# 1. Configurar servidor VPN
sudo -E ~/.venvs/midgard/bin/raijin-server vpn

# 2. Adicionar clientes
sudo -E ~/.venvs/midgard/bin/raijin-server vpn-client

# 3. Configurar DNS interno (opcional, mas muito útil!)
sudo -E ~/.venvs/midgard/bin/raijin-server internal-dns
```

Após conectar à VPN, acesse diretamente:
- `http://grafana.asgard.internal`
- `http://prometheus.asgard.internal`
- `http://minio.asgard.internal`

### Opção 2: Port-Forward via SSH

```bash
# Grafana
ssh -L 3000:localhost:3000 usuario@servidor
kubectl port-forward svc/grafana -n observability 3000:80

# Acesse: http://localhost:3000
```

### Opção 3: Script Automatizado

```bash
# Iniciar todos os port-forwards
~/raijin-server/scripts/port-forward-all.sh start

# Parar
~/raijin-server/scripts/port-forward-all.sh stop
```

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura técnica do ambiente |
| [SECURITY.md](SECURITY.md) | Políticas de segurança |
| [AUDIT.md](AUDIT.md) | Relatório de auditoria |
| [docs/VERSIONING.md](docs/VERSIONING.md) | Versionamento e tags |
| [docs/INFRASTRUCTURE_GUIDE.md](docs/INFRASTRUCTURE_GUIDE.md) | Guia completo de infraestrutura |
| [docs/VPN_REMOTE_ACCESS.md](docs/VPN_REMOTE_ACCESS.md) | Configuração de VPN |
| [docs/INTERNAL_DNS.md](docs/INTERNAL_DNS.md) | DNS interno para domínios privados |
| [docs/VISUAL_TOOLS.md](docs/VISUAL_TOOLS.md) | Ferramentas visuais (Lens, K9s) |
| [docs/SSH_WINDOWS.md](docs/SSH_WINDOWS.md) | Acesso SSH do Windows |
| [docs/MINIO_OPERATIONS.md](docs/MINIO_OPERATIONS.md) | Operações do MinIO |

---

## Comandos Úteis

```bash
# Atalho para o comando (após ativar venv)
alias raijin='sudo -E ~/.venvs/midgard/bin/raijin-server'

# Exemplos
raijin --version
raijin validate
raijin menu
raijin --dry-run kubernetes
```

### Logs e Debug

```bash
# Ver logs do CLI
raijin debug logs --lines 200

# Seguir logs em tempo real
raijin debug logs --follow

# Snapshot do cluster
raijin debug kube --events 100
```

---

## Desenvolvimento

### Instalar em modo dev

```bash
# Clonar repositório
git clone https://github.com/rafaelluisdacostacoelho/raijin-server
cd raijin-server

# Criar venv de desenvolvimento
python3 -m venv .venv
source .venv/bin/activate

# Instalar em modo editável
pip install -e ".[dev]"

# Rodar testes
pytest
```

### Publicar no PyPI

```bash
# 1. Configurar credenciais PyPI
# Crie o arquivo ~/.pypirc com seu token:
cat > ~/.pypirc << 'EOF'
[pypi]
username = __token__
password = pypi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
chmod 600 ~/.pypirc

# 2. Criar venv limpo para publicação
python3 -m venv ~/.venvs/publish
source ~/.venvs/publish/bin/activate
pip install -U pip build twine

# 3. Build e publicar
./release.sh X.X.X
```

---

## Destaques

- ✅ **Validações automáticas** de pré-requisitos
- ✅ **Health checks** após cada instalação
- ✅ **Retry inteligente** com backoff exponencial
- ✅ **Logging estruturado** com rotação
- ✅ **Modo dry-run** para simular mudanças
- ✅ **Idempotente** - re-execução segura
- ✅ **VPN-first** - dashboards seguros por padrão

---

## Licença

MIT License - veja [LICENSE](LICENSE) para detalhes.
