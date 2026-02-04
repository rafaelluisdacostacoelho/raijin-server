# Changelog

Todas as alterações notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [1.0.0] - Em Desenvolvimento

### ✨ Adicionado

#### Configuração via Environment Variables
- Novo arquivo `.env.example` com template completo de todas as variáveis
- Variáveis `RAIJIN_*` para configuração de:
  - Rede: `RAIJIN_NET_INTERFACE`, `RAIJIN_NET_IP`, `RAIJIN_NET_GATEWAY`, `RAIJIN_NET_DNS`
  - Kubernetes: `RAIJIN_K8S_VERSION`, `RAIJIN_K8S_POD_CIDR`, `RAIJIN_K8S_SERVICE_CIDR`
  - MetalLB: `RAIJIN_METALLB_POOL_START`, `RAIJIN_METALLB_POOL_END`
  - VPN: `RAIJIN_VPN_PORT`, `RAIJIN_VPN_SUBNET`, `RAIJIN_VPN_ENDPOINT`
  - SSH: `RAIJIN_SSH_PORT`, `RAIJIN_SSH_ALLOWED_USERS`
  - Storage: `RAIJIN_MINIO_*`, `RAIJIN_HARBOR_*`
  - Observabilidade: `RAIJIN_GRAFANA_*`, `RAIJIN_LOKI_*`, `RAIJIN_PROMETHEUS_*`

#### Módulo `network_config.py`
- Novo módulo para gerenciar configuração de rede via environment variables
- Comandos:
  - `raijin network-config show` - Mostra config atual vs env vars
  - `raijin network-config apply` - Aplica config do .env
  - `raijin network-config restore` - Restaura backup anterior
- Backup automático antes de aplicar mudanças
- Detecção automática de interfaces disponíveis
- Validação de IP/CIDR

#### Módulo `vpn_manager.py`
- Novo módulo para pausar/retomar VPN WireGuard
- Comandos:
  - `raijin vpn-control status` - Status detalhado da VPN
  - `raijin vpn-control pause` - Pausa VPN (fecha porta, reduz superfície de ataque)
  - `raijin vpn-control resume` - Retoma VPN
  - `raijin vpn-control schedule` - Agendamento automático (ativa das 8h às 22h)
- Integração com UFW para gerenciar firewall
- Estado persistente em `/var/lib/raijin-server/vpn-state`
- Cron jobs para agendamento

#### Módulo `ssh_manager.py`
- Novo módulo para habilitar/desabilitar SSH
- Comandos:
  - `raijin ssh-control status` - Status do SSH com métricas de segurança
  - `raijin ssh-control enable` - Habilita SSH
  - `raijin ssh-control disable` - Desabilita SSH (com confirmação de segurança)
  - `raijin ssh-control port <N>` - Muda porta do SSH
  - `raijin ssh-control schedule` - Agendamento automático
- Análise de configurações de segurança (password auth, root login, allowed users)
- Proteção contra lockout acidental

#### Documentação Completa
- 19 novos arquivos de documentação em `docs/tools/`
- Glossário de termos e siglas em cada documento
- Navegação entre documentos relacionados
- Exemplos práticos e troubleshooting
- Documentos criados:
  - kubernetes.md, helm.md, metallb.md, bootstrap.md
  - loki.md, prometheus.md, grafana.md
  - istio.md, kong.md, argo.md
  - Atualizações em: calico.md, cert-manager.md, traefik.md
  - secrets.md, velero.md, harbor.md, minio.md, vault.md

#### Backlog v2.0.0
- Documento `docs/BACKLOG_V2.md` com roadmap detalhado
- Planejamento de módulos:
  - `worker.py` - Gerenciamento de workers
  - `cluster.py` - Operações de cluster multi-node
  - `storage.py` - Integração com NAS (Synology, TrueNAS)
  - `multiwan.py` - Multi-link internet
  - `poweredge.py` - Suporte Dell PowerEdge

### 🔄 Alterado
- CLI atualizado com novos subcomandos
- Imports reorganizados para incluir novos módulos

### 🔒 Segurança
- Dados sensíveis removidos do código-fonte
- Configuração via environment variables
- Ferramentas para reduzir superfície de ataque (VPN/SSH pause)

---

## [0.2.38] - Versão Atual

### Funcionalidades Existentes
- Full install automatizado
- Módulos: bootstrap, hardening, network, essentials, firewall
- VPN WireGuard com gerenciamento de clientes
- Kubernetes com kubeadm
- CNI Calico
- MetalLB LoadBalancer
- Traefik Ingress Controller
- Cert-Manager com ACME
- Istio Service Mesh
- Kong API Gateway
- MinIO Object Storage
- Prometheus + Grafana
- Loki Logs
- Harbor Registry
- Argo CD/Workflows
- Velero Backup
- External Secrets + Vault

---

## Notas de Migração

### De 0.2.x para 1.0.0

1. **Criar arquivo `.env`**:
   ```bash
   cp .env.example .env
   # Editar com suas configurações
   ```

2. **Variáveis obrigatórias**:
   ```bash
   RAIJIN_NET_INTERFACE=enp1s0
   RAIJIN_NET_IP=192.168.1.100/24
   RAIJIN_NET_GATEWAY=192.168.1.1
   RAIJIN_NET_DNS=1.1.1.1
   ```

3. **Verificar configuração**:
   ```bash
   raijin network-config show
   ```

4. **Aplicar se necessário**:
   ```bash
   raijin network-config apply
   ```

---

## Links

- [Documentação](docs/)
- [Backlog v2.0.0](docs/BACKLOG_V2.md)
- [Guia de Contribuição](CONTRIBUTING.md)
