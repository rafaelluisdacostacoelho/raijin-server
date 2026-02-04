# Loki — Agregação de Logs

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Bootstrap](bootstrap.md) | [Próximo: Prometheus →](prometheus.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Queries](#queries-logql)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[Loki](#1-loki)¹** é um sistema de agregação de logs inspirado no Prometheus.
- Indexa apenas **[labels](#2-labels)²** (não o conteúdo dos logs) → armazenamento eficiente.
- **[LogQL](#3-logql)³**: Linguagem de query similar ao PromQL.

## Por que usamos
- **Custo reduzido**: Indexação mínima vs Elasticsearch.
- **Integração nativa**: Grafana + Loki out-of-the-box.
- **Multi-tenant**: Isolamento de logs por namespace/tenant.
- **Retention flexível**: Configurar retenção por stream (7d, 30d, 90d).

## Como está configurado no Raijin (V1)
- **Versão**: Loki 2.9+ (Helm chart `grafana/loki`)
- **Namespace**: `observability`
- **Modo**: **[Monolithic](#4-monolithic-mode)⁴** (single binary, ideal para <50GB/dia)
- **Storage**: MinIO S3 (`s3://loki-chunks/`)
- **Retenção**: 30 dias (configurável via `limits_config.retention_period`)
- **Ingestion**: Promtail (DaemonSet em cada node)
- **Acesso**: Integrado no Grafana (datasource `Loki`)

## Como operamos

### Ver logs via Grafana

```logql
# Acessar Grafana → Explore → Datasource: Loki

# Logs de namespace
{namespace="traefik"} |= "error"

# Logs de pod específico
{namespace="minio", pod=~"minio-.*"} | json | level="error"

# Buscar texto
{namespace="cert-manager"} |= "certificate" |= "issued"

# Rate de logs
rate({namespace="traefik"}[5m])
```

### Queries via CLI (LogCLI)

```bash
# Instalar logcli
go install github.com/grafana/loki/cmd/logcli@latest

# Configurar endpoint
export LOKI_ADDR=http://loki.observability.svc:3100

# Buscar logs
logcli query '{namespace="traefik"}' --limit=100 --since=1h

# Follow logs (tail -f)
logcli query '{namespace="traefik"}' --tail --since=10m

# Buscar pattern
logcli query '{namespace="minio"} |= "error"' --since=24h
```

### Gerenciar retenção

```bash
# Ver configuração de retenção
kubectl get cm loki -n observability -o yaml | grep retention

# Editar retenção (via values.yaml)
# limits_config:
#   retention_period: 720h  # 30 dias

helm upgrade loki grafana/loki \
  -n observability \
  -f loki-values.yaml
```

## Queries LogQL

### Básicas

```logql
# Todos logs de um namespace
{namespace="traefik"}

# Logs de múltiplos namespaces
{namespace=~"traefik|minio|harbor"}

# Filtrar por label
{app="nginx", env="production"}

# Buscar texto (case-insensitive)
{namespace="traefik"} |= "error"

# Excluir texto
{namespace="traefik"} != "healthcheck"

# Regex
{namespace="traefik"} |~ "HTTP/[12]\\.[01] [45]\\d{2}"
```

### Parsing

```logql
# Parse JSON
{namespace="traefik"} | json | level="error"

# Parse logfmt
{namespace="istio-system"} | logfmt | status_code >= 500

# Pattern matching
{namespace="nginx"} | pattern `<ip> - - <_> "<method> <path> <_>" <status> <_>`

# Extrair campos
{namespace="traefik"} | regexp `(?P<status>\d{3})` | status >= "500"
```

### Agregação

```logql
# Contar logs
count_over_time({namespace="traefik"}[5m])

# Rate de logs
rate({namespace="traefik"}[1m])

# Sum de bytes
sum(rate({namespace="traefik"} | json | unwrap bytes [5m])) by (pod)

# Top 10 pods com mais erros
topk(10, sum by (pod) (rate({namespace="traefik"} |= "error" [5m])))

# Percentil de latência
quantile_over_time(0.95, {namespace="traefik"} | json | unwrap latency [5m])
```

### Alerting

```logql
# Alta taxa de erros
sum(rate({namespace="traefik"} |= "error" [5m])) > 10

# Logs de falha em deploy
count_over_time({namespace="argocd"} |= "failed" [10m]) > 5

# Certificado próximo da expiração
{namespace="cert-manager"} |= "certificate expires in less than"
```

## Troubleshooting

### Loki não recebe logs

```bash
# Verificar pods Loki
kubectl get pods -n observability -l app=loki

# Ver logs do Loki
kubectl logs -n observability -l app=loki --tail=100

# Verificar Promtail (ingestion)
kubectl get pods -n observability -l app=promtail
kubectl logs -n observability -l app=promtail | grep -i error

# Testar endpoint Loki
kubectl port-forward -n observability svc/loki 3100:3100
curl http://localhost:3100/ready
```

### Promtail não envia logs

```bash
# Ver config do Promtail
kubectl get cm promtail -n observability -o yaml

# Verificar scrape_configs
# Deve incluir /var/log/pods/*/*.log

# Ver targets descobertos
kubectl port-forward -n observability svc/promtail 3101:3101
curl http://localhost:3101/targets

# Logs do Promtail
kubectl logs -n observability <promtail-pod> | grep -E "error|warn"
```

### Grafana não mostra datasource Loki

```bash
# Verificar datasource configurado
kubectl exec -n observability <grafana-pod> -- cat /etc/grafana/provisioning/datasources/loki.yaml

# Testar conectividade Grafana → Loki
kubectl exec -n observability <grafana-pod> -- wget -qO- http://loki.observability.svc:3100/ready

# Ver logs Grafana
kubectl logs -n observability <grafana-pod> | grep -i loki
```

### Query lenta

```bash
# Reduzir time range
{namespace="traefik"}[5m]  # Em vez de [24h]

# Adicionar mais labels
{namespace="traefik", pod="traefik-abc123"}

# Evitar regex complexos
|~ ".*error.*"  # LENTO
|= "error"      # RÁPIDO

# Usar pipeline filtering
{namespace="traefik"} |= "error" | json | level="error"
```

## Glossário

### 1. Loki
**Loki**: Sistema de agregação de logs da Grafana Labs; indexa apenas labels (não conteúdo).
- **[grafana.com/oss/loki](https://grafana.com/oss/loki/)**

### 2. Labels
**Labels**: Metadata key-value anexado a streams de logs (namespace, pod, job).

### 3. LogQL
**LogQL**: Linguagem de query do Loki; similar ao PromQL com suporte a grep/regex.
- **[grafana.com/docs/loki/latest/logql](https://grafana.com/docs/loki/latest/logql/)**

### 4. Monolithic Mode
**Monolithic Mode**: Deploy Loki single-binary (ingester+querier+compactor); ideal para <50GB/dia.

### 5. Promtail
**Promtail**: Agente de coleta de logs; roda como DaemonSet e envia logs para Loki.

### 6. Stream
**Stream**: Conjunto de logs com mesmo labelset (ex.: `{namespace="traefik", pod="xyz"}`).

### 7. Chunk
**Chunk**: Bloco comprimido de logs armazenado no object storage (S3/MinIO).

### 8. LogCLI
**LogCLI**: CLI oficial do Loki para queries via terminal.

### 9. Multi-tenancy
**Multi-tenancy**: Isolamento de logs por tenant ID (via header `X-Scope-OrgID`).

### 10. Compactor
**Compactor**: Componente que compacta chunks antigos e aplica retenção.

---

## Exemplos práticos

### Instalar via Helm

```bash
# Adicionar repo
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Values customizado
cat << EOF > loki-values.yaml
loki:
  commonConfig:
    replication_factor: 1
  storage:
    type: s3
    s3:
      endpoint: minio.minio.svc:9000
      bucketnames: loki-chunks
      access_key_id: loki
      secret_access_key: supersecret
      s3forcepathstyle: true
      insecure: true
  limits_config:
    retention_period: 720h  # 30 dias
    max_query_length: 721h

# Modo monolithic
deploymentMode: SingleBinary
singleBinary:
  replicas: 1
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2
      memory: 4Gi
EOF

# Instalar
helm install loki grafana/loki \
  -n observability \
  --create-namespace \
  -f loki-values.yaml
```

### Instalar Promtail

```bash
cat << EOF > promtail-values.yaml
config:
  clients:
    - url: http://loki.observability.svc:3100/loki/api/v1/push

  snippets:
    scrapeConfigs: |
      - job_name: kubernetes-pods
        kubernetes_sd_configs:
          - role: pod
        relabel_configs:
          - source_labels: [__meta_kubernetes_namespace]
            target_label: namespace
          - source_labels: [__meta_kubernetes_pod_name]
            target_label: pod
          - source_labels: [__meta_kubernetes_container_name]
            target_label: container
EOF

helm install promtail grafana/promtail \
  -n observability \
  -f promtail-values.yaml
```

### Queries úteis

```logql
# Top 10 pods com mais logs
topk(10, sum by (pod) (rate({namespace="default"}[5m])))

# Erros por container
sum by (container) (rate({namespace="traefik"} |= "error" [5m]))

# Latência P95
quantile_over_time(0.95, {namespace="traefik"} | json | unwrap latency_ms [5m])

# Logs únicos (deduplicação)
count_over_time({namespace="traefik"} | pattern `<_> <msg>` [5m]) by (msg)

# Timeline de eventos
{namespace="cert-manager"} |= "certificate" | json | line_format "{{.ts}} {{.msg}}"
```

### Alertas Prometheus

```yaml
# prometheus-rules.yaml
groups:
- name: loki
  rules:
  - alert: HighErrorRate
    expr: |
      sum(rate({namespace="traefik"} |= "error" [5m])) > 10
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Alta taxa de erros no Traefik"

  - alert: LokiDown
    expr: up{job="loki"} == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Loki indisponível"
```

---

## Boas práticas ✅

1. **Labels essenciais**: namespace, pod, container (evitar high-cardinality).
2. **Retenção adequada**: 7d dev, 30d staging, 90d+ prod.
3. **Object storage**: S3/MinIO para chunks (não usar disco local).
4. **Promtail em DaemonSet**: Garante coleta em todos os nodes.
5. **Compactor habilitado**: Limpa chunks antigos automaticamente.
6. **Multi-tenancy**: Separar tenants em clusters compartilhados.
7. **Query limits**: `max_query_length` para evitar queries gigantes.
8. **Monitorar ingestão**: Alertar em `loki_ingester_bytes_received`.
9. **Parse estruturado**: Usar `| json` para logs JSON.
10. **Evitar regex complexos**: Usar `|=` (grep) em vez de `|~` (regex).
11. **Agregação no query time**: Não pré-agregar logs (Loki faz isso).
12. **LogCLI para debug**: Testar queries antes de criar dashboards.
13. **Stream sharding**: Distribuir streams grandes entre ingesters.
14. **Cache habilitado**: Reduzir latência de queries repetidas.
15. **Backup de configs**: Versionar `loki-values.yaml` no Git.

---

## Práticas ruins ❌

1. **Labels com alta cardinalidade**: `user_id`, `request_id` como labels.
2. **Sem retenção**: Armazenar logs indefinidamente.
3. **Disco local para chunks**: Perder logs em falha de node.
4. **Promtail não configurado**: Logs não chegam no Loki.
5. **Query sem labels**: `{}` retorna TODOS os logs (lento).
6. **Regex em labels**: `{pod=~".*traefik.*"}` (usar `{pod=~"traefik-.*"}`).
7. **Time range gigante**: `[24h]` em queries exploratórias.
8. **Não monitorar ingestão**: Descobrir problema só quando logs somem.
9. **Compactor desabilitado**: Chunks antigos acumulam.
10. **Sem recursos adequados**: OOMKilled em ingester.
11. **Logs não estruturados**: Dificulta parsing e agregação.
12. **Multi-line logs truncados**: Configurar `max_line_size`.
13. **Sem backup**: Perder configuração e dashboards.
14. **Query alerts frequentes**: Sobrecarga no Loki.
15. **Ignorar métricas Loki**: Não monitorar `loki_request_duration_seconds`.

---

## Diagnóstico avançado

### Métricas Loki

```bash
# Port-forward Loki
kubectl port-forward -n observability svc/loki 3100:3100

# Métricas Prometheus
curl http://localhost:3100/metrics | grep loki_

# Taxa de ingestão
loki_distributor_bytes_received_total

# Latência de queries
loki_query_duration_seconds

# Chunks em memória
loki_ingester_memory_chunks
```

### Debug Promtail

```bash
# Targets descobertos
kubectl port-forward -n observability <promtail-pod> 3101:3101
curl http://localhost:3101/targets | jq

# Ver labels extraídos
curl http://localhost:3101/targets | jq '.activeTargets[0].labels'

# Logs enviados
curl http://localhost:3101/metrics | grep promtail_sent_entries_total
```

### Verificar storage S3

```bash
# Listar chunks no MinIO
mc ls minio/loki-chunks/fake/

# Tamanho do bucket
mc du minio/loki-chunks/

# Ver index
mc ls minio/loki-chunks/index/
```

### Query performance

```bash
# Habilitar query stats
{namespace="traefik"} | stats

# Ver splits de query
kubectl logs -n observability <loki-pod> | grep "split queries"

# Cache hits
curl http://localhost:3100/metrics | grep loki_cache_fetched_keys
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Bootstrap](bootstrap.md)** | **[Próximo: Prometheus →](prometheus.md)**
