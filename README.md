# raijin-server

CLI em Python (Typer) para automatizar setup e hardening de servidores Ubuntu Server em ambientes produtivos. Orquestra rede, firewall, Kubernetes, observabilidade e backups para acelerar a subida de clusters e workloads.

**✨ Versão Auditada e Resiliente para Produção**

## Destaques

- ✅ **Validações de Pré-requisitos**: OS, espaço em disco, memória, conectividade
- ✅ **Health Checks Automáticos**: Valida serviços após instalação
- ✅ **Retry Inteligente**: Resistente a falhas temporárias de rede
- ✅ **Logging Estruturado**: Logs persistentes para auditoria
- ✅ **Gestão de Dependências**: Garante ordem correta de execução
- ✅ **Configuração via Arquivo**: Automação completa com YAML/JSON
- ✅ **Idempotência**: Re-execução segura sem quebrar o sistema
- ✅ **Modo Dry-run**: Simula execução sem aplicar mudanças

## Requisitos

- Python >= 3.9
- Ubuntu Server 20.04+ (testado em 24.04)
- Permissões root/sudo
- Conectividade com internet
- Mínimo 4GB RAM, 20GB disco livre
- Ferramentas: `curl`, `apt-get`, `systemctl`

Ferramentas adicionais (instaladas pelos módulos quando necessário):
- `helm` (>=3.8 para OCI)
- `kubectl`, `kubeadm`
- `velero`, `istioctl`

## Instalacao

Sem venv (global):

```bash
python -m pip install .
```

Com venv (recomendado para desenvolvimento):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Uso rapido

### Validar Sistema
```bash
# Verifica se o sistema atende pré-requisitos
sudo raijin-server validate
```

### Menu Interativo
```bash
# Menu visual com stautils.py`: Funções utilitárias com retry, timeout e logging.
- `src/raijin_server/validators.py`: Validações de pré-requisitos e dependências.
- `src/raijin_server/healthchecks.py`: Health checks pós-instalação.
- `src/raijin_server/config.py`: Gerenciamento de configuração via arquivo.
- `src/raijin_server/modules/`: Automações por tópico (hardening, network, essentials, firewall, kubernetes, calico, istio, traefik, kong, minio, prometheus, grafana, loki, harness, velero, kafka).
- `scripts/`: Espaço para shells e templates auxiliares.
- `ARCHITECTURE.md`: Visão do desenho técnico.
- `AUDIT.md`: Relatório completo de auditoria e melhorias.
- `SECURITY.md`: Como reportar vulnerabilidades
### Execução Direta de Módulos
```bash
# Executar módulo específico
sudo raijin-server kubernetes

# Dry-run (simula sem aplicar)
sudo raijin-server --dry-run kubernetes

# Pular validações (não recomendado)
sudo raijin-server --skip-validation kubernetes
```

### Automação via Arquivo de Configuração
```bash
# Gerar template de configuração
ra✅ Validações de pré-requisitos e health-check por módulo
- ✅ Gestão automática de dependências entre módulos
- ✅ Sistema de logging estruturado e persistente
- ✅ Retry automático e timeouts configuráveis
- ✅ Configuração via arquivo YAML/JSON
- ✅ Provisionar ingress seguro para Grafana/Prometheus/Alertmanager (modulo `observability-ingress`)
- ✅ Dashboards e alertas opinativos prontos para uso (modulo `observability-dashboards`)
- ⏳ Suporte a sealed-secrets/external-secrets para credenciais
- ⏳ Testes automatizados (pytest) e linters
- ⏳ Rollback automático em falhas
- ⏳ Modo de instalação mínima vs completa

## Documentação Adicional

- **[AUDIT.md](AUDIT.md)**: Relatório completo de auditoria e melhorias implementadas
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Arquitetura técnica do ambiente
- **[SECURITY.md](SECURITY.md)**: Políticas de segurança e reporte de vulnerabilidades

## Fluxo de Execução Recomendado

```bash
# 1. Validar sistema
sudo raijin-server validate

# 2. Base do sistema
sudo raijin-server essentials
sudo raijin-server hardening
sudo raijin-server network
sudo raijin-server firewall

# 3. Kubernetes
sudo raijin-server kubernetes
sudo raijin-server calico

# 4. Ingress (escolha um)
sudo raijin-server traefik
# OU
sudo raijin-server kong

# 5. Observabilidade
sudo raijin-server prometheus
sudo raijin-server grafana
sudo raijin-server observability-ingress
sudo raijin-server observability-dashboards
sudo raijin-server loki

# 6. Storage e Mensageria (opcional)
sudo raijin-server minio
sudo raijin-server kafka

# 7. Backup
sudo raijin-server velero

# 8. Service Mesh (opcional)
sudo raijin-server istio
```
# Executar com configuração
sudo raijin-server --config production.yaml kubernetes
```

### Comandos Úteis
```bash
# Versão
raijin-server version

# Monitorar logs
tail -f /var/log/raijin-server/raijin-server.log
```

## Estrutura

- `src/raijin_server/cli.py`: CLI principal com Typer, banner e `--dry-run`.
- `src/raijin_server/modules/`: automacoes por topico (hardening, network, essentials, firewall, kubernetes, calico, istio, traefik, kong, minio, prometheus, grafana, loki, harness, velero, kafka).
- `scripts/`: espaco para shells e templates.
- `ARCHITECTURE.md`: visao do desenho atual.
- `SECURITY.md`: como reportar e pensar seguranca.

## Modulos disponiveis

- `sanitize`: remove clusters/residuos kube*, binarios antigos e listas apt.
- `bootstrap`: instala helm, kubectl, istioctl, velero, containerd e dependencias.
- `ssh-hardening`: cria usuario dedicado, aplica politicas seguras de SSH e integra ao Fail2ban.
- `hardening`: fail2ban, unattended-upgrades, sysctl.
- `essentials`: pacotes base (curl, git, jq, etc.) e NTP.
- `network`: Netplan com IP fixo e DNS.
- `firewall`: UFW com regras para SSH/HTTP/HTTPS/K8s.
- `vpn`: provisiona WireGuard (servidor + cliente inicial) e libera firewall.
- `kubernetes`: kubeadm init, containerd SystemdCgroup, kubeconfig.
- `calico`: CNI Calico com CIDR custom e policy default-deny.
- `istio`: istioctl install (perfil raijin) e injeção automática.
- `traefik`: IngressController com TLS/ACME.
- `kong`: Ingress/Gateway com Helm.
- `minio`: armazenamento S3 compatível via Helm.
- `prometheus`, `grafana`, `loki`: observabilidade, dashboards e persistencia.
- `observability-ingress`: autentica e publica Grafana/Prometheus/Alertmanager com TLS dedicado.
- `observability-dashboards`: aplica dashboards opinativos e alertas default (Grafana/Prometheus/Alertmanager).
- `harness`: delegate Helm com parametros interativos.
- `velero`: backup/restore com schedule.
- `kafka`: deploy Bitnami via OCI.
- `full-install`: orquestra toda a sequência automaticamente (sanitize ➜ observability-dashboards).

## Roadmap basico

- ✅ Validacoes de pre-requisitos e health-check por modulo.
- ✅ Provisionar ingress seguro para Grafana/Prometheus/Alertmanager (modulo `observability-ingress`).
- ✅ Dashboards e alertas opinativos prontos para uso (modulo `observability-dashboards`).
- ⏳ Suporte a sealed-secrets/external-secrets para credenciais.
- ⏳ Testes automatizados (pytest) e linters.

## Proximos passos sugeridos

- Suporte a sealed-secrets/external-secrets para credenciais sensíveis.
- Adicionar validacoes e testes (pytest, linters, testcontainers).
- Empacotar scripts auxiliares em `scripts/` e referencia-los nos modulos.

## Acesso remoto seguro (VPN + SSH)

Execute `raijin-server ssh-hardening` para aplicar as politicas abaixo automaticamente e `raijin-server vpn` para subir o servidor WireGuard com um cliente inicial. Use `--dry-run` se quiser apenas revisar os comandos.

1. **SSH reforçado**
	- Gere chaves `ed25519` em cada estação: `ssh-keygen -t ed25519 -C "adminops@empresa"`.
	- No servidor, crie um usuário administrativo (ex.: `adminops`) e aplique hardening no `/etc/ssh/sshd_config`:
	  ```
	  Port 22           # altere caso deseje
	  PermitRootLogin no
	  PasswordAuthentication no
	  AllowUsers adminops
	  ```
	- Copie as chaves públicas para `/home/adminops/.ssh/authorized_keys`, ajuste permissões e reinicie o sshd (`systemctl restart ssh`).
	- Para tunelar dashboards internos sem expor portas, use `ssh -L 3000:localhost:3000 adminops@IP_PUBLICO` (ou `-R` para acesso reverso).

2. **VPN privada (WireGuard sugerido)**
	- Instale `wireguard-tools` e `qrencode`, gere chaves do servidor (`wg genkey | tee server.key | wg pubkey > server.pub`).
	- Configure `/etc/wireguard/wg0.conf`:
	  ```
	  [Interface]
	  Address = 10.20.0.1/24
	  ListenPort = 51820
	  PrivateKey = <server.key>
	  PostUp = ufw route allow in on wg0 out on eth0
	  PostDown = ufw route delete allow in on wg0 out on eth0
	  ```
	- Adicione um `[Peer]` por estação com `AllowedIPs = 10.20.0.X/32`, distribua os arquivos `clientX.conf` ou QR codes e inicie com `systemctl enable --now wg-quick@wg0`.
	- No modem/VPC, libere apenas `51820/UDP` e limite SSH/UIs para o range `10.20.0.0/24` (UFW `allow from 10.20.0.0/24 to any port 22`).

3. **Fluxo recomendado**
	- Exporte apenas o que precisa ser público (Traefik, Harness) e mantenha Grafana/Prometheus/Kubernetes API restritos ao túnel VPN.
	- Documente as portas encaminhadas e mantenha as chaves/tokens em `secrets/` ou sealed-secrets para fácil rotação.

	Combine esse fluxo com `raijin-server observability-ingress` para publicar Grafana/Prometheus/Alertmanager somente via TLS dedicado e autenticação básica por Traefik e finalize com `raijin-server observability-dashboards` para carregar dashboards e alertas opinativos.
