# raijin-server

CLI em Python (Typer) para automatizar setup e hardening de servidores Ubuntu Server em ambientes produtivos. Orquestra rede, firewall, Kubernetes, observabilidade e backups para acelerar a subida de clusters e workloads.

**✨ Versão Auditada e Resiliente para Produção**

## Links úteis

- Repositório: https://github.com/rafaelluisdacostacoelho/raijin-server
- Documentação completa: [docs/INFRASTRUCTURE_GUIDE.md](docs/INFRASTRUCTURE_GUIDE.md)
- Arquitetura: [ARCHITECTURE.md](ARCHITECTURE.md)
- Auditoria: [AUDIT.md](AUDIT.md)
- Segurança: [SECURITY.md](SECURITY.md)

## Destaques

- ✅ **Validações de Pré-requisitos**: OS, espaço em disco, memória, conectividade, ambiente Python (venv)
- ✅ **Health Checks Automáticos**: Valida serviços após instalação
- ✅ **Retry Inteligente com Backoff**: Resistente a falhas temporárias de rede (5 tentativas, backoff exponencial)
- ✅ **Logging Estruturado**: Logs persistentes com rotação (20MB, 5 backups)
- ✅ **Gestão de Dependências**: Garante ordem correta de execução
- ✅ **Verificação de Cluster**: Módulos que dependem de K8s verificam disponibilidade antes de executar
- ✅ **Clean Automático**: Opção de limpar instalação anterior ao re-executar kubernetes
- ✅ **IPv4 Only**: IPv6 desabilitado por padrão para simplificar rede
- ✅ **Configuração via Arquivo**: Automação completa com YAML/JSON
- ✅ **Idempotência**: Re-execução segura sem quebrar o sistema
- ✅ **Modo Dry-run**: Simula execução sem aplicar mudanças

## Requisitos

## Instalação (sempre em venv midgard)

Use apenas o venv `~/.venvs/midgard` para padronizar ambiente e logs.

```bash
# 1) Criar/reativar venv midgard
python3 -m venv ~/.venvs/midgard
source ~/.venvs/midgard/bin/activate
pip install -U pip setuptools

# 2) Instalar a partir do source (dev)
pip install -U raijin-server

# 3) Uso com sudo preservando o venv
sudo -E ~/.venvs/midgard/bin/raijin-server --version
sudo -E ~/.venvs/midgard/bin/raijin-server validate
sudo -E ~/.venvs/midgard/bin/raijin-server full-install

# 4) Quando terminar
deactivate
```

> Dica: se precisar reinstalar, remova o venv (`rm -rf ~/.venvs/midgard`), recrie e repita o passo 2. O `-E` no sudo mantém o venv ativo para o Python.

# 5. Rodar usando root preservando o venv
sudo -E ~/.venvs/raijin/bin/raijin-server --version
sudo -E ~/.venvs/raijin/bin/raijin-server validate
sudo -E ~/.venvs/raijin/bin/raijin-server full-install

# 6. Para sair do venv quando terminar
deactivate
```

> **Nota**: O `-E` no sudo preserva as variáveis de ambiente, garantindo que o Python use o venv correto mesmo como root.

## Uso rapido

### Validar Sistema
```bash
# Verifica se o sistema atende pré-requisitos
sudo -E ~/.venvs/midgard/bin/raijin-server validate
```

### Menu Interativo
```bash
# Menu visual com atalho para módulos
sudo -E ~/.venvs/midgard/bin/raijin-server menu
```

### Execução Direta de Módulos
```bash
# Executar módulo específico
sudo -E ~/.venvs/midgard/bin/raijin-server kubernetes

# Dry-run (simula sem aplicar)
sudo -E ~/.venvs/midgard/bin/raijin-server --dry-run kubernetes

# Pular validações (não recomendado)
sudo -E ~/.venvs/midgard/bin/raijin-server --skip-validation kubernetes
```

### Instalação Completa com seleção de passos
```bash
# Rodar tudo (padrão)
sudo -E ~/.venvs/midgard/bin/raijin-server full-install

# Escolher passos antes de rodar
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --select-steps

# Definir lista fixa (ordem original preservada)
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --steps "kubernetes,calico,cert_manager,traefik"

# Pedir confirmação a cada módulo
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --confirm-each

# Modo debug: snapshots + diagnose pós-módulo
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --debug-mode

# Apenas snapshots após cada módulo (pós-kubernetes)
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --snapshots

# Apenas diagnose pós-módulo (ex.: cert-manager)
sudo -E ~/.venvs/midgard/bin/raijin-server full-install --post-diagnose
```

### Depuração e Logs (pós-Kubernetes)
```bash
# Ver todos os logs do CLI com pager (less)
sudo -E ~/.venvs/midgard/bin/raijin-server debug logs --lines 400

# Seguir logs em tempo real
sudo -E ~/.venvs/midgard/bin/raijin-server debug logs --follow

# Snapshot do cluster: nodes, pods e eventos (últimos 200)
sudo -E ~/.venvs/midgard/bin/raijin-server debug kube --events 200

# Focar em um namespace (ex.: cert-manager)
sudo -E ~/.venvs/midgard/bin/raijin-server debug kube --namespace cert-manager --events 150

# Consultar logs do kubelet via journalctl
sudo -E ~/.venvs/midgard/bin/raijin-server debug journal --service kubelet --lines 300

# Consultar outro serviço systemd (ex.: containerd)
sudo -E ~/.venvs/midgard/bin/raijin-server debug journal --service containerd --lines 200
```

### Automação via Arquivo de Configuração
## Documentação Adicional

- **[AUDIT.md](AUDIT.md)**: Relatório completo de auditoria e melhorias implementadas
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Arquitetura técnica do ambiente
- **[SECURITY.md](SECURITY.md)**: Políticas de segurança e reporte de vulnerabilidades

## Fluxo de Execução Recomendado

```bash
# 1. Validar sistema
sudo -E ~/.venvs/midgard/bin/raijin-server validate

# 2. Base do sistema
sudo -E ~/.venvs/midgard/bin/raijin-server essentials
sudo -E ~/.venvs/midgard/bin/raijin-server hardening
sudo -E ~/.venvs/midgard/bin/raijin-server network   # OPCIONAL: pule se IP já configurado via provedor ISP
sudo -E ~/.venvs/midgard/bin/raijin-server firewall

# 3. Kubernetes
sudo -E ~/.venvs/midgard/bin/raijin-server kubernetes
sudo -E ~/.venvs/midgard/bin/raijin-server calico
sudo -E ~/.venvs/midgard/bin/raijin-server secrets
sudo -E ~/.venvs/midgard/bin/raijin-server cert-manager

# 4. Ingress (escolha um)
sudo -E ~/.venvs/midgard/bin/raijin-server traefik
# OU
sudo -E ~/.venvs/midgard/bin/raijin-server kong

# 5. Observabilidade
sudo -E ~/.venvs/midgard/bin/raijin-server prometheus
sudo -E ~/.venvs/midgard/bin/raijin-server grafana
sudo -E ~/.venvs/midgard/bin/raijin-server observability-ingress
sudo -E ~/.venvs/midgard/bin/raijin-server observability-dashboards
sudo -E ~/.venvs/midgard/bin/raijin-server loki

# 6. Storage e Mensageria (opcional)
sudo -E ~/.venvs/midgard/bin/raijin-server minio
sudo -E ~/.venvs/midgard/bin/raijin-server kafka

# 7. Backup
sudo -E ~/.venvs/midgard/bin/raijin-server velero

# 8. Service Mesh (opcional)
sudo -E ~/.venvs/midgard/bin/raijin-server istio
```

### IP Estático (pular se já configurado)

O módulo `network` é **opcional** quando:
- O IP fixo foi configurado pelo provedor ISP (ex: Ibi Internet Empresarial)
- O IP estático foi definido durante a instalação do Ubuntu Server
- A rede já está funcionando corretamente

Para pular automaticamente em automações:
```bash
export RAIJIN_SKIP_NETWORK=1
sudo -E ~/.venvs/midgard/bin/raijin-server full-install
```

O módulo detecta automaticamente se já existe um Netplan com IP estático e pergunta
se deseja pular. Se executar manualmente, basta responder "não" quando perguntado.

### Notas de kernel / Secure Boot
- WireGuard depende de módulo de kernel. Com Secure Boot ativo, o módulo DKMS pode precisar ser assinado; se `modprobe wireguard` falhar, assine ou desabilite Secure Boot temporariamente.
- Certifique-se de ter headers do kernel instalados (`/lib/modules/$(uname -r)/build`) antes de instalar WireGuard.
- Para Kubernetes/Calico é necessário `br_netfilter` e sysctl `bridge-nf-call-iptables=1`. O módulo `bootstrap` já aplica, mas verifique se seu kernel suporta.

### Comandos Úteis
```bash
# Versão (flag ou comando)
~/.venvs/midgard/bin/raijin-server --version
~/.venvs/midgard/bin/raijin-server -V
~/.venvs/midgard/bin/raijin-server version

# Monitorar logs
sudo -E ~/.venvs/midgard/bin/raijin-server debug logs --follow

# Rotacao de logs (default: 20MB, 5 backups)
# Ajuste via env:
#   export RAIJIN_LOG_MAX_BYTES=$((50*1024*1024))
#   export RAIJIN_LOG_BACKUP_COUNT=5

# Métrica de tamanho de logs (Prometheus/Grafana) usando node_exporter textfile collector
# 1) Habilite textfile collector (ex.: /var/lib/node_exporter/textfile_collector)
# 2) Agende o script:
#    sudo /bin/bash -c 'RAIJIN_METRIC_FILE=/var/lib/node_exporter/textfile_collector/raijin_log_size.prom \
#      RAIJIN_LOG_DIR=/var/log/raijin-server \
#      /usr/bin/bash -l $(python - <<'PY'
#from raijin_server.utils import resolve_script_path
#print(resolve_script_path("log_size_metric.sh"))
#PY
#)'
# 3) Crie um painel no Grafana com a métrica `raijin_log_size_total_bytes` (Prometheus)
```

## Estrutura

- `src/raijin_server/cli.py`: CLI principal com Typer, banner e `--dry-run`.
- `src/raijin_server/modules/`: automacoes por topico (hardening, network, essentials, firewall, kubernetes, calico, istio, traefik, kong, minio, prometheus, grafana, loki, harness, velero, kafka).
- `src/raijin_server/scripts/`: shells embarcados acessíveis via `raijin_server.utils.resolve_script_path()`.
- `ARCHITECTURE.md`: visao do desenho atual.
- `SECURITY.md`: como reportar e pensar seguranca.

## Modulos disponiveis

- `sanitize`: remove clusters/residuos kube*, binarios antigos e listas apt.
- `bootstrap`: instala helm, kubectl, istioctl, velero, containerd e dependencias.
- `ssh-hardening`: cria usuario dedicado, aplica politicas seguras de SSH e integra ao Fail2ban.
- `hardening`: fail2ban, unattended-upgrades, sysctl.
- `essentials`: pacotes base (curl, git, jq, etc.) e NTP.
- `network`: Netplan com IP fixo e DNS. **OPCIONAL** se IP já configurado pelo provedor ISP.
- `firewall`: UFW com regras para SSH/HTTP/HTTPS/K8s.
- `vpn`: provisiona WireGuard (servidor + cliente inicial) e libera firewall.
- `kubernetes`: kubeadm init, containerd SystemdCgroup, kubeconfig. **Oferece limpeza automática** se detectar instalação anterior. IPv6 desabilitado por padrão.
- `calico`: CNI Calico com CIDR custom, default-deny e opcao de liberar egress rotulado. **Verifica cluster ativo** antes de aplicar.
- `cert_manager`: instala cert-manager e ClusterIssuer ACME (HTTP-01/DNS-01). **Verifica cluster ativo** antes de instalar.
- `secrets`: instala sealed-secrets e external-secrets via Helm.
- `istio`: istioctl install (perfil raijin) e injeção automática.
- `traefik`: IngressController com TLS/ACME.
- `kong`: Ingress/Gateway com Helm.
- `minio`: armazenamento S3 compatível via Helm.
- `prometheus`, `grafana`, `loki`: observabilidade, dashboards e persistencia.
- `observability-ingress`: autentica e publica Grafana/Prometheus/Alertmanager com TLS dedicado.
- `observability-dashboards`: aplica dashboards opinativos e alertas default (Grafana/Prometheus/Alertmanager).
- `apokolips-demo`: landing page temática para validar ingress/TLS e testar DNS externo.
- `harness`: delegate Helm com parametros interativos.
- `velero`: backup/restore com schedule.
- `kafka`: deploy Bitnami via OCI.
- `full-install`: orquestra toda a sequência automaticamente (sanitize ➜ observability-dashboards).

## Roadmap basico

- ✅ Validacoes de pre-requisitos e health-check por modulo.
- ✅ Provisionar ingress seguro para Grafana/Prometheus/Alertmanager (modulo `observability-ingress`).
- ✅ Dashboards e alertas opinativos prontos para uso (modulo `observability-dashboards`).
- ✅ Suporte a sealed-secrets/external-secrets para credenciais.
- ⏳ Testes automatizados (pytest) e linters.

## Proximos passos sugeridos

- Suporte a sealed-secrets/external-secrets para credenciais sensíveis.
- Adicionar validacoes e testes (pytest, linters, testcontainers).

## Scripts embarcados

Todos os helpers shell agora vivem em `src/raijin_server/scripts/` e acompanham o pacote Python.
Para invocá-los dentro de um módulo (ou mesmo após instalar via `pip`), use o helper `resolve_script_path()`:

```bash
SCRIPT_PATH=$(python - <<'PY'
from raijin_server.utils import resolve_script_path
print(resolve_script_path('pre-deploy-check.sh'))
PY
)

bash "$SCRIPT_PATH"
```

O helper garante o caminho absoluto correto independentemente de onde o pacote foi instalado.

## Teste de ingress (Apokolips)

O módulo [src/raijin_server/modules/apokolips_demo.py](src/raijin_server/modules/apokolips_demo.py) cria um namespace dedicado, ConfigMap com HTML, Deployment NGINX, Service e Ingress Traefik com uma landing page "Apokolips" para validar o tráfego externo.

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server apokolips-demo
```

Personalização rápida:

- Defina `APOKOLIPS_HOST=ingress.seudominio.com` para pular o prompt de host.
- Defina `APOKOLIPS_TLS_SECRET=nome-do-secret` caso já possua um Secret TLS pronto (caso contrário o módulo publica apenas HTTP).

Recursos criados:

- Namespace `apokolips-demo`
- ConfigMap com o HTML temático
- Deployment + Service `ClusterIP` baseado em `nginx:1.25`
- Ingress (`ingressClassName: traefik`) apontando para o host informado

Valide o acesso:

```bash
kubectl -n apokolips-demo get ingress apokolips-demo -o wide
curl -H "Host: SEU_HOST" https://<IP_DO_LOAD_BALANCER>/ --insecure
```

Para remover rapidamente:

```bash
kubectl delete namespace apokolips-demo
```

## Liberar egress controlado para pods

O módulo `calico` agora gera um `default-deny` por namespace e oferece uma política opcional
`allow-egress-internet`. Ao responder "sim" para a pergunta de egress, basta rotular os workloads
que precisam falar com APIs externas:

```bash
kubectl label deployment minha-api -n backend \
	networking.raijin.dev/egress=internet
```

Somente pods com esse label terão tráfego liberado para o CIDR definido (padrão `0.0.0.0/0`).
Isso permite manter o isolamento padrão enquanto libera acesso seletivo para integrações externas.

## Automacao de segredos (sealed-secrets + external-secrets)

Execute o modulo `secrets` para instalar os controladores:

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server secrets
```

Passos realizados:
- Instala `sealed-secrets` (namespace padrao: `kube-system`)
- Instala `external-secrets` (namespace padrao: `external-secrets`, com CRDs)
- Opcional: exporta o certificado publico do sealed-secrets para gerar manifests lacrados via `kubeseal`

Dicas rapidas:
- Exportar certificado depois: `kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key -o jsonpath='{.items[0].data.tls\.crt}' | base64 -d > sealed-secrets-cert.pem`
- Gerar sealed secret local: `kubeseal --controller-namespace kube-system --controller-name sealed-secrets < secret.yaml > sealed.yaml`
- ESO: crie um `SecretStore`/`ClusterSecretStore` apontando para seu backend (AWS/GCP/Vault) e um `ExternalSecret` referenciando as chaves.

### Validar o modulo `secrets`

```bash
# Status dos releases
helm status sealed-secrets -n kube-system
helm status external-secrets -n external-secrets

# Pods prontos
kubectl get pods -n kube-system -l name=sealed-secrets
kubectl get pods -n external-secrets -l app.kubernetes.io/name=external-secrets

# Health check integrado
raijin-server --health-check secrets
```

### Exemplos (prontos para aplicar)

- SecretStore AWS Secrets Manager: [examples/secrets/secretstore-aws-sm.yaml](examples/secrets/secretstore-aws-sm.yaml)
- ExternalSecret AWS Secrets Manager: [examples/secrets/externalsecret-aws-sm.yaml](examples/secrets/externalsecret-aws-sm.yaml)
- SecretStore Vault AppRole: [examples/secrets/secretstore-vault-approle.yaml](examples/secrets/secretstore-vault-approle.yaml)
- ExternalSecret Vault: [examples/secrets/externalsecret-vault.yaml](examples/secrets/externalsecret-vault.yaml)

Notas rápidas:
- Para AWS/IRSA: crie um ServiceAccount (`apps/eso-aws`) anotado com o role IAM e garanta a policy para leitura dos secrets.
- Para Vault: crie o Secret `vault-approle-secret` com `secretId` e ajuste `ROLE_ID_AQUI`. Ajuste `server`/`path` conforme seu mount de KV.
- Aplique na ordem: SecretStore ➜ ExternalSecret ➜ valide `kubectl get secret` no namespace do app.

## Testes e lint

Ambiente de dev:
```bash
python -m pip install -e .[dev]
pytest
ruff check src tests
```

## Publicar no PyPI (Twine)

O Twine é a ferramenta oficial para enviar pacotes Python ao PyPI com upload seguro (HTTPS e checagem de hash). Use sempre um token de API.

Passo a passo:
```bash
# 1) Gere artefatos
python -m build --sdist --wheel --outdir dist/

# 2) Configure o token (crie em https://pypi.org/manage/account/token/)
export TWINE_USERNAME=__token__
export TWINE_PASSWORD="<seu-token>"

# 3) Envie para o PyPI
python -m twine upload dist/*

# 4) Verifique instalação
python -m pip install -U raijin-server
raijin-server --version
```

Boas práticas:
- Use venv dedicado para publicar (`python -m venv ~/.venvs/publish && source ~/.venvs/publish/bin/activate`).
- Nunca commite ou exponha o token; mantenha em variável de ambiente/secret manager.
- Sempre suba primeiro para TestPyPI se quiser validar (`--repository testpypi`).

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
