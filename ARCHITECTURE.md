# Arquitetura do ambiente (esperada)

## Visao macro (ASCII)

```
 [Users/CI/CD]
		|
	[Ingress]
 (Traefik/Kong) -- TLS/ACME, WAF, rate limit
		|
	[Service Mesh]
 Istio (mTLS, traffic split)
		|
  +---+------------+
  |                |
[Workloads]    [Data]
(Apps/Jobs)  (MinIO, Kafka)
  |                |
  +-------+--------+
			 |
	 [Observability]
 (Prometheus -> Grafana, Loki -> Grafana)
			 |
		 [Backup]
		  Velero
```

## Fluxo de provisao (CLI)

1. Sistema/base: `essentials`, `hardening`, `network`, `firewall`.
2. Cluster: `kubernetes` (kubeadm + containerd + kubeconfig).
3. Rede/CNI: `calico` (CIDR custom + default-deny).
4. Entrada: `traefik` ou `kong` (TLS/ACME, ingressClass).
5. Mallha/servicos: `istio` opcional.
6. Dados: `minio`, `kafka` via Helm/OCI.
7. Observabilidade: `prometheus`, `grafana`, `loki` (dashboards e datasources provisionados).
8. Backup: `velero` com schedule.
9. Add-ons CI/CD: `harness` delegate.

## Metodologia modular

- Cada modulo exposto como subcomando Typer (`raijin-server <modulo>`), com suporte a `--dry-run`.
- **Idempotente**: Repos, chaves GPG, namespaces e releases Helm reusam o estado existente. Verificações impedem re-execução destrutiva.
- **Resiliente**: Retry automático (3x default), timeouts configuráveis (300s), logging estruturado.
- **Validado**: Health checks pós-instalação garantem que serviços subiram corretamente.
- **Rastreável**: Logs persistentes em `/var/log/raijin-server/` ou `~/.raijin-server.log`.
- **Automatizável**: Configuração via arquivo YAML/JSON para execução não-interativa.
- **Dependências Gerenciadas**: Sistema verifica e bloqueia execução fora de ordem.
- Placeholders prontos para extensao via `scripts/` (templates e shell helpers).
- Configuracao guiada por prompts (CIDR, ingress host, senhas admin, storage, tokens) para adaptar ao ambiente.

## Futuro/prioridades

- ✅ ~~Health-check pos-provisionamento (smoke tests) por modulo.~~ **CONCLUÍDO**
- ✅ ~~Validacao de pre-requisitos (root, OS, conectividade, binarios).~~ **CONCLUÍDO**
- ✅ ~~Sistema de logging estruturado e persistente.~~ **CONCLUÍDO**
- ✅ ~~Gestão automática de dependências entre módulos.~~ **CONCLUÍDO**
- ✅ ~~Configuração via arquivo YAML/JSON.~~ **CONCLUÍDO**
- Gate de seguranca: sealed-secrets/external-secrets, policies (OPA/Gatekeeper ou Kyverno).
- Ingress seguro para observabilidade (Grafana/Alertmanager) com auth/IPS allowlist.
- Testes automatizados (pytest) com cobertura de código.
- Rollback automático em falhas.
- Modo de instalação mínima vs completa.

## Componentes Arquiteturais

### Camada de Validação (`validators.py`)
- Pré-requisitos de sistema (OS, memória, disco, conectividade)
- Dependências entre módulos
- Permissões de execução

### Camada de Execução (`utils.py`)
- Retry automático com backoff
- Timeouts configuráveis
- Logging estruturado
- Execução de comandos resiliente

### Camada de Verificação (`healthchecks.py`)
- Validação de serviços systemd
- Status de pods Kubernetes
- Releases Helm deployed
- Portas listening
- Wait conditions com timeout

### Camada de Configuração (`config.py`)
- Parser YAML/JSON
- Templates de configuração
- Merge de configs interativas + arquivo

### Camada de Apresentação (`cli.py`)
- Menu interativo com status visual
- Comandos diretos por módulo
- Modo dry-run
- Integração de todas as camadas

## Fluxo de Execução Completo

```
1. [CLI] Recebe comando do usuário
   ↓
2. [Validators] Valida pré-requisitos do sistema
   ↓
3. [Validators] Verifica dependências do módulo
   ↓
4. [Module] Executa lógica específica
   ├─ [Utils] Executa comandos com retry
   ├─ [Utils] Grava logs estruturados
   └─ [Config] Usa configurações de arquivo/prompts
   ↓
5. [Health Checks] Valida serviços instalados
   ↓
6. [State] Marca módulo como concluído
   ↓
7. [CLI] Exibe resumo (avisos/erros)
```

## Garantias de Resiliência

1. **Retry Automático**: Até 3 tentativas em comandos críticos
2. **Timeouts**: Limite de 300s por operação (configurável)
3. **Health Checks**: Validação automática pós-instalação
4. **Logging**: Auditoria completa de todas as operações
5. **Idempotência**: Re-execução segura sem efeitos colaterais
6. **Dependências**: Ordem de execução garantida
7. **Rollback**: Estado rastreável para reversão (futuro)
