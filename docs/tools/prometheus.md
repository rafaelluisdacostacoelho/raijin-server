# Prometheus — Métricas e Alertas

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Loki](loki.md) | [Próximo: Grafana →](grafana.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Queries PromQL](#queries-promql)
- [Alerting](#alerting)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[Prometheus](#1-prometheus)¹** é o sistema de **[métricas](#2-metric)²** e alertas padrão CNCF.
- **[Pull-based](#3-pull-based)³**: Prometheus scrape endpoints HTTP (`/metrics`).
- **[PromQL](#4-promql)⁴**: Linguagem de query para agregação e análise.

## Por que usamos
- **Padrão K8s**: Service discovery automático de pods/services.
- **Multi-dimensional**: Métricas com labels (`http_requests_total{method="GET", status="200"}`).
- **Alerting integrado**: AlertManager para notificações (Slack, PagerDuty).
- **Ecossistema rico**: 100+ exporters oficiais (node_exporter, blackbox, etc).

## Como está configurado no Raijin (V1)
- **Versão**: Prometheus 2.49+ via **kube-prometheus-stack** (Helm chart)
- **Namespace**: `observability`
- **Componentes**:
  - **Prometheus Server**: Coleta e armazena métricas
  - **AlertManager**: Gerencia alertas e notificações
  - **Prometheus Operator**: Gerencia CRDs (ServiceMonitor, PrometheusRule)
  - **Node Exporter**: Métricas de nodes (CPU, RAM, disco)
  - **kube-state-metrics**: Métricas de recursos K8s (Pods, Deployments)
- **Retenção**: 15 dias (configurável via `retention`)
- **Storage**: PVC 50Gi (local-path ou Longhorn)
- **Acesso**: Integrado no Grafana (datasource `Prometheus`)

## Como operamos

### Acessar UI Prometheus

```bash
# Port-forward Prometheus
kubectl port-forward -n observability svc/prometheus-kube-prometheus-prometheus 9090:9090

# Abrir http://localhost:9090
# Status → Targets: Ver todos os endpoints scraped
# Graph: Executar queries PromQL
```

### Queries via API

```bash
# Query instantânea
curl 'http://prometheus.observability.svc:9090/api/v1/query?query=up'

# Query range (últimas 1h)
curl 'http://prometheus.observability.svc:9090/api/v1/query_range?query=rate(http_requests_total[5m])&start=2024-01-01T00:00:00Z&end=2024-01-01T01:00:00Z&step=15s'

# Ver targets
curl 'http://prometheus.observability.svc:9090/api/v1/targets'
```

### Criar ServiceMonitor

```yaml
# Expor métricas custom
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: myapp
  namespace: observability
spec:
  selector:
    matchLabels:
      app: myapp
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

### Criar alerta

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: myapp-alerts
  namespace: observability
spec:
  groups:
  - name: myapp
    rules:
    - alert: HighErrorRate
      expr: |
        rate(http_requests_total{status=~"5.."}[5m]) > 0.1
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Alta taxa de erros em {{ $labels.pod }}"
```

## Queries PromQL

### Básicas

```promql
# Valor instantâneo
up

# Filtrar por labels
up{job="kubernetes-nodes"}

# Regex em labels
http_requests_total{path=~"/api/.*"}

# Operadores
http_requests_total > 1000
http_requests_total == 200

# Agregação
sum(http_requests_total)
avg(http_requests_total) by (pod)
max(node_memory_MemAvailable_bytes) by (node)
```

### Rate e aumentos

```promql
# Rate (requisições/segundo nos últimos 5min)
rate(http_requests_total[5m])

# Irate (rate instantâneo, últimos 2 pontos)
irate(http_requests_total[5m])

# Increase (total nos últimos 5min)
increase(http_requests_total[5m])

# Delta (diferença)
delta(cpu_usage[5m])
```

### Agregação multi-dimensional

```promql
# Sum por pod
sum(rate(http_requests_total[5m])) by (pod)

# Top 10 pods com mais CPU
topk(10, sum(rate(container_cpu_usage_seconds_total[5m])) by (pod))

# Percentil 95 de latência
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Count de pods por namespace
count(kube_pod_info) by (namespace)
```

### Operações matemáticas

```promql
# Percentual de CPU usado
100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))

# Memória disponível em GB
node_memory_MemAvailable_bytes / 1024 / 1024 / 1024

# Taxa de erro (%)
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

## Alerting

### AlertManager config

```yaml
# alertmanager-config.yaml
global:
  slack_api_url: 'https://hooks.slack.com/services/XXX'

route:
  receiver: 'default'
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 12h
  routes:
  - match:
      severity: critical
    receiver: 'pagerduty'

receivers:
- name: 'default'
  slack_configs:
  - channel: '#alerts'
    title: '{{ .GroupLabels.alertname }}'
    text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'

- name: 'pagerduty'
  pagerduty_configs:
  - service_key: 'XXX'
```

### Alertas comuns

```yaml
groups:
- name: infrastructure
  rules:
  - alert: NodeDown
    expr: up{job="kubernetes-nodes"} == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Node {{ $labels.instance }} down"

  - alert: HighCPU
    expr: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
    for: 10m
    labels:
      severity: warning

  - alert: HighMemory
    expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90
    for: 5m
    labels:
      severity: critical

  - alert: DiskSpaceLow
    expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 10
    for: 5m
    labels:
      severity: warning

  - alert: PodCrashLooping
    expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
    for: 5m
    labels:
      severity: warning
```

## Troubleshooting

### Targets não descobertos

```bash
# Ver targets no Prometheus UI
# Status → Targets

# Ver ServiceMonitors
kubectl get servicemonitors -n observability

# Ver PrometheusRules
kubectl get prometheusrules -n observability

# Verificar labels do Prometheus
kubectl get prometheus -n observability -o yaml | grep serviceMonitorSelector

# Exemplo: Prometheus só scrape ServiceMonitors com label prometheus: kube-prometheus
```

### Scrape failures

```bash
# Ver logs do Prometheus
kubectl logs -n observability prometheus-kube-prometheus-prometheus-0

# Testar endpoint manualmente
kubectl port-forward -n <namespace> <pod> 8080:8080
curl http://localhost:8080/metrics

# Verificar NetworkPolicy bloqueando
kubectl get netpol -n <namespace>
```

### AlertManager não enviando

```bash
# Ver status AlertManager
kubectl port-forward -n observability svc/alertmanager-operated 9093:9093
# http://localhost:9093/#/alerts

# Ver config
kubectl get secret alertmanager-kube-prometheus-alertmanager -n observability -o jsonpath='{.data.alertmanager\.yaml}' | base64 -d

# Logs
kubectl logs -n observability alertmanager-kube-prometheus-alertmanager-0
```

### Métricas ausentes

```bash
# Verificar se pod expõe /metrics
kubectl exec -n <namespace> <pod> -- wget -qO- http://localhost:8080/metrics

# Ver ServiceMonitor
kubectl get servicemonitor -n observability <name> -o yaml

# Verificar se Service tem label correto
kubectl get svc -n <namespace> <service> --show-labels
```

## Glossário

### 1. Prometheus
**Prometheus**: Sistema de monitoramento e alertas CNCF; coleta métricas time-series via HTTP.
- **[prometheus.io](https://prometheus.io/)**

### 2. Metric
**Metric**: Time-series de medições numéricas com labels (ex.: `http_requests_total{method="GET"}`).

### 3. Pull-based
**Pull-based**: Modelo onde Prometheus busca métricas ativamente (vs push no Graphite/InfluxDB).

### 4. PromQL
**PromQL**: Linguagem de query do Prometheus para agregação e análise de métricas.
- **[prometheus.io/docs/prometheus/latest/querying/basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)**

### 5. ServiceMonitor
**ServiceMonitor**: CRD do Prometheus Operator que define targets de scrape (Services K8s).

### 6. PrometheusRule
**PrometheusRule**: CRD que define regras de alertas e recording rules.

### 7. AlertManager
**AlertManager**: Componente que agrupa, deduplicam e roteia alertas (Slack, email, PagerDuty).
- **[prometheus.io/docs/alerting/latest/alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)**

### 8. Exporter
**Exporter**: Aplicação que expõe métricas no formato Prometheus (node_exporter, mysqld_exporter).

### 9. Scrape
**Scrape**: Ação de coletar métricas de um endpoint HTTP.

### 10. Recording Rule
**Recording Rule**: Query PromQL pré-computada e armazenada (otimização para dashboards).

---

## Exemplos práticos

### Instalar kube-prometheus-stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

cat << EOF > prometheus-values.yaml
prometheus:
  prometheusSpec:
    retention: 15d
    storageSpec:
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 50Gi
    resources:
      requests:
        cpu: 500m
        memory: 2Gi
      limits:
        cpu: 2
        memory: 8Gi

alertmanager:
  alertmanagerSpec:
    storage:
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 10Gi

grafana:
  enabled: true
  adminPassword: admin123

nodeExporter:
  enabled: true

kubeStateMetrics:
  enabled: true
EOF

helm install prometheus prometheus-community/kube-prometheus-stack \
  -n observability \
  --create-namespace \
  -f prometheus-values.yaml
```

### Expor métricas custom (Go)

```go
package main

import (
    "net/http"
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
    httpRequestsTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "http_requests_total",
            Help: "Total HTTP requests",
        },
        []string{"method", "path", "status"},
    )
)

func init() {
    prometheus.MustRegister(httpRequestsTotal)
}

func handler(w http.ResponseWriter, r *http.Request) {
    httpRequestsTotal.WithLabelValues(r.Method, r.URL.Path, "200").Inc()
    w.Write([]byte("Hello"))
}

func main() {
    http.HandleFunc("/", handler)
    http.Handle("/metrics", promhttp.Handler())
    http.ListenAndServe(":8080", nil)
}
```

### Recording rules

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: recording-rules
  namespace: observability
spec:
  groups:
  - name: aggregations
    interval: 30s
    rules:
    - record: job:http_requests:rate5m
      expr: sum(rate(http_requests_total[5m])) by (job)
    
    - record: instance:node_cpu:avg
      expr: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

### Dashboards úteis

```promql
# CPU por pod
sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod)

# Memória por pod (MB)
sum(container_memory_working_set_bytes{pod!=""}) by (pod) / 1024 / 1024

# Network RX/TX (MB/s)
sum(rate(container_network_receive_bytes_total[5m])) / 1024 / 1024
sum(rate(container_network_transmit_bytes_total[5m])) / 1024 / 1024

# P95 latency HTTP
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))

# Taxa de erro HTTP
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

---

## Boas práticas ✅

1. **Labels essenciais**: namespace, pod, job (evitar high-cardinality como user_id).
2. **ServiceMonitor por app**: Um ServiceMonitor para cada aplicação.
3. **Retenção adequada**: 15d dev, 30d staging, 90d prod.
4. **Storage persistente**: PVC para não perder métricas.
5. **Recording rules**: Pré-computar queries complexas de dashboards.
6. **Alertas com `for`**: Evitar flapping (ex.: `for: 5m`).
7. **Annotations em alertas**: Incluir context (runbook, dashboard link).
8. **AlertManager routes**: Rotear por severidade (critical → PagerDuty).
9. **Rate em counters**: Sempre usar `rate()` em counters (não valor bruto).
10. **Histogram para latência**: Usar `histogram_quantile()` para percentis.
11. **Node exporter habilitado**: Métricas de CPU/RAM/disco essenciais.
12. **Monitorar Prometheus**: Criar alertas para o próprio Prometheus.
13. **Limites de recursos**: Evitar OOMKilled no Prometheus.
14. **Scrape interval adequado**: 30s padrão (15s para apps críticos).
15. **Backup de configs**: Versionar PrometheusRules no Git.

---

## Práticas ruins ❌

1. **Labels com alta cardinalidade**: `user_id`, `request_id`, `session_id` como labels.
2. **Scrape interval muito curto**: <15s sobrecarrega Prometheus.
3. **Sem retenção**: Armazenar métricas indefinidamente.
4. **Storage efêmero**: Perder métricas em restart de pod.
5. **Alertas sem `for`**: Flapping constante (alerta → resolve → alerta).
6. **Annotations vazias**: Alertas sem context ("Pod down" - qual pod?).
7. **Query diretamente counters**: Usar `http_requests_total` sem `rate()`.
8. **Histogram sem labels**: Não conseguir filtrar latência por endpoint.
9. **Não monitorar Prometheus**: Descobrir que Prometheus caiu quando dashboards quebram.
10. **Scrape de endpoints externos**: Usar Blackbox exporter para HTTP checks externos.
11. **Recording rules desnecessários**: Pré-computar queries simples.
12. **Múltiplos AlertManagers sem HA**: Perder alertas em falha.
13. **Sem limites de recursos**: Prometheus consome toda RAM do node.
14. **Exporters não atualizados**: Métricas deprecated ou incorretas.
15. **Alertas para tudo**: Alert fatigue; focar em SLOs críticos.

---

## Diagnóstico avançado

### Métricas do Prometheus

```promql
# Taxa de ingestão (samples/s)
rate(prometheus_tsdb_head_samples_appended_total[5m])

# Tamanho do banco (GB)
prometheus_tsdb_storage_blocks_bytes / 1024 / 1024 / 1024

# Latência de queries
histogram_quantile(0.95, rate(prometheus_http_request_duration_seconds_bucket[5m]))

# Scrapes com falha
rate(prometheus_target_scrapes_exceeded_sample_limit_total[5m])
```

### Debug de targets

```bash
# Ver targets no Prometheus
curl http://prometheus.observability.svc:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health=="down")'

# Ver ServiceMonitors descobertos
kubectl get servicemonitors -A

# Verificar seletor do Prometheus
kubectl get prometheus -n observability -o jsonpath='{.items[0].spec.serviceMonitorSelector}'
```

### Otimização de queries

```promql
# LENTO: Agregação sem filtro
sum(rate(http_requests_total[5m]))

# RÁPIDO: Filtrar antes de agregar
sum(rate(http_requests_total{namespace="traefik"}[5m]))

# LENTO: Regex complexo
http_requests_total{path=~".*api.*user.*"}

# RÁPIDO: Prefix match
http_requests_total{path=~"/api/.*"}
```

### Verificar cardinality

```promql
# Count de séries por métrica
count({__name__=~".+"}) by (__name__)

# Top 10 métricas com mais séries
topk(10, count by (__name__)({__name__=~".+"}))

# Cardinality de labels
count(count by (pod)({__name__=~".+"}))
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Loki](loki.md)** | **[Próximo: Grafana →](grafana.md)**
