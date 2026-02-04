# Observabilidade (Prometheus, Grafana, Loki, Alertmanager)

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Traefik](traefik.md) | [Próximo: Secrets →](secrets.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Consultas rápidas](#consultas-rápidas)
- [Troubleshooting](#troubleshooting)
- [Manutenção](#manutenção-e-monitoramento)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- Stack de métricas, dashboards, logs e alertas instalada via **kube-prometheus-stack⁵**.
- Componentes ficam no namespace `observability`.
- **Prometheus¹**: coleta e armazena métricas time-series.
- **Grafana²**: dashboards e visualização.
- **Loki³**: agregação e consulta de logs.
- **Alertmanager⁴**: gerenciamento e roteamento de alertas.

## Por que usamos
- **Métricas**: Prometheus coleta/alimenta alertas; queries **PromQL⁶**.
- **Dashboards**: Grafana para visualização unificada.
- **Logs**: Loki para consulta centralizada; queries **LogQL⁷**.
- **Alertas**: Alertmanager para roteamento (email/Slack/PagerDuty).
- Stack integrada com service discovery automático do Kubernetes.

## Como está configurado no Raijin (V1)
- Stack instalada via `kube-prometheus-stack` (Operator) no namespace `observability`.
- Prometheus, Alertmanager e Grafana expostos internamente (acesso via port-forward ou VPN); Loki instalado e configurado como datasource no Grafana.
- Dashboards padrão do kube-prometheus para nodes, pods e control plane já disponíveis no Grafana.
- Alertmanager configurado; rotas/finalizações devem ser ajustadas conforme o ambiente (e-mail/webhook/chat).

## O que resolve na nossa arquitetura
- Visibilidade unificada de métricas, logs e alertas do cluster e das aplicações.
- Dashboards prontos para saúde do Kubernetes e componentes core.
- Centralização de logs com Loki, reduzindo necessidade de acessar nodes para depurar.

## Como operamos
- Prometheus: `kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n observability` e acessar http://localhost:9090.
- Grafana: `kubectl port-forward svc/grafana 3000:80 -n observability` e acessar http://localhost:3000.
- Loki via Grafana: datasource Loki já configurado; use consultas LogQL.
- Alertmanager: `kubectl port-forward svc/kube-prometheus-stack-alertmanager 9093:9093 -n observability`.

## Consultas rápidas
### PromQL (Prometheus)
- CPU de pod: `rate(container_cpu_usage_seconds_total{namespace="default",pod=~"minha-app.*"}[5m])`.
- Memória de pod: `container_memory_working_set_bytes{namespace="default",pod=~"minha-app.*"}`.
- Requests HTTP (Traefik): `rate(traefik_service_requests_total{service="myapp@kubernetes"}[5m])`.
- Erros 5xx: `sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) by (service)`.

### LogQL (Loki via Grafana)
- Logs de app: `{namespace="default", app="minha-app"}`.
- Erros últimos 5min: `{namespace="default", app="minha-app"} |= "error" [5m]`.
- Rate de logs: `rate({namespace="default", app="minha-app"}[5m])`.

## Troubleshooting
- Ver pods: `kubectl get pods -n observability`.
- Logs de Prometheus: `kubectl logs -n observability -l app.kubernetes.io/name=prometheus`.
- Logs de Loki: `kubectl logs -n observability -l app.kubernetes.io/name=loki`.
- Checar alertas ativos: acessar Alertmanager (port-forward acima) e conferir status.

## Manutenção e monitoramento
- Saúde: `kubectl get pods -n observability`; observar reinícios anormais.
- Armazenamento de métricas: garantir espaço/retention do Prometheus (config do chart) e do Loki (persistência conforme o ambiente).
- Alertas: revisar silences e rotas no Alertmanager; manter contatos atualizados.
- Dashboards: versionar dashboards customizados para evitar perda em upgrades; preferir provisionamento por ConfigMap/sidecar do chart.
- Upgrades: aplicar primeiro em staging; checar mudanças de CRDs do Prometheus Operator.

## Links úteis
- Prometheus Operator: https://prometheus-operator.dev/
- Grafana: https://grafana.com/docs/
- Loki: https://grafana.com/docs/loki/latest/

---

## Glossário

1. **Prometheus**: Sistema de monitoramento time-series que coleta métricas via scrape HTTP.
2. **Grafana**: Plataforma de visualização e dashboards para múltiplas fontes de dados.
3. **Loki**: Sistema de agregação de logs inspirado no Prometheus (não indexa conteúdo, apenas labels).
4. **Alertmanager**: Gerencia alertas do Prometheus (agrupamento, silencing, roteamento).
5. **kube-prometheus-stack**: Helm chart que instala Prometheus, Grafana, Alertmanager, exporters e ServiceMonitors.
6. **PromQL** (Prometheus Query Language): Linguagem de consulta para métricas time-series.
7. **LogQL**: Linguagem de consulta do Loki (sintaxe similar ao PromQL).
8. **ServiceMonitor**: CRD do Prometheus Operator que define scrape targets automáticos.
9. **PrometheusRule**: CRD que define regras de alerta e recording rules.
10. **Exporter**: Processo que expõe métricas em formato Prometheus (node-exporter, kube-state-metrics).
11. **Scrape**: Coleta periódica de métricas via HTTP GET em `/metrics`.
12. **Time Series**: Sequência de valores indexados por timestamp.
13. **Recording Rule**: Query pre-computada para otimizar dashboards complexos.
14. **Silence**: Supressão temporária de alertas no Alertmanager.
15. **Datasource**: Fonte de dados configurada no Grafana (Prometheus, Loki, etc).

---

## Exemplos práticos

### PromQL: Consultas úteis

```promql
# Top 5 pods por uso de CPU
topk(5, rate(container_cpu_usage_seconds_total{namespace="apps"}[5m]))

# Memória disponível no node
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100

# Taxa de requests por segundo (Traefik)
sum(rate(traefik_service_requests_total[5m])) by (service)

# Latência P95 de requests
histogram_quantile(0.95, rate(traefik_service_request_duration_seconds_bucket[5m]))

# Pods reiniciando
rate(kube_pod_container_status_restarts_total[15m]) > 0

# Disco usado por pod
container_fs_usage_bytes{namespace="apps"} / container_fs_limit_bytes * 100
```

### LogQL: Consultas úteis

```logql
# Logs de erro últimas 24h
{namespace="apps", app="backend"} |= "error" [24h]

# Rate de logs por segundo
rate({namespace="apps"}[5m])

# Filtrar por level e contar
sum(rate({namespace="apps"} | json | level="error" [5m])) by (pod)

# Logs de latência alta
{namespace="apps"} | json | latency > 500

# Padrão regex
{namespace="apps"} |~ "(?i)exception|error|fail"

# Top 10 pods com mais logs
topk(10, sum(rate({namespace="apps"}[5m])) by (pod))
```

### Criar PrometheusRule customizada

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: custom-alerts
  namespace: observability
spec:
  groups:
  - name: apps
    interval: 30s
    rules:
    - alert: HighErrorRate
      expr: sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) by (service) > 0.1
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Alta taxa de erros 5xx em {{ $labels.service }}"
        description: "{{ $value }} req/s com erro 5xx"
```

### Configurar rota de alerta no Alertmanager

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-kube-prometheus-stack-alertmanager
  namespace: observability
stringData:
  alertmanager.yaml: |
    route:
      receiver: 'default'
      group_by: ['alertname', 'cluster']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 12h
      routes:
      - match:
          severity: critical
        receiver: pagerduty
      - match:
          severity: warning
        receiver: slack
    receivers:
    - name: 'default'
      webhook_configs:
      - url: 'http://webhook.example.com/alert'
    - name: 'slack'
      slack_configs:
      - api_url: 'https://hooks.slack.com/services/XXX'
        channel: '#alerts'
    - name: 'pagerduty'
      pagerduty_configs:
      - service_key: 'YOUR_KEY'
```

---

## Boas práticas ✅

1. **Labels consistentes**: Usar labels padronizados em todos os workloads (`app`, `tier`, `env`).
2. **Retention adequado**: Configurar retention do Prometheus (15 dias padrão) conforme necessidade.
3. **Recording rules**: Pre-computar queries complexas para otimizar dashboards.
4. **Alertas acionáveis**: Criar alertas apenas para condições que exigem ação imediata.
5. **Silencing planejado**: Silenciar alertas durante manutenções programadas.
6. **Dashboards versionados**: Exportar e versionar dashboards em Git (ConfigMaps ou sidecar).
7. **Logs estruturados**: Emitir logs em JSON para melhor parseamento no Loki.
8. **Rate limiting em queries**: Evitar queries muito abrangentes sem filtros (namespace, pod).
9. **High Availability**: Em produção, rodar múltiplas réplicas de Prometheus/Alertmanager.
10. **Backup de Grafana**: Exportar datasources e dashboards periodicamente.
11. **ServiceMonitor por app**: Criar ServiceMonitor para expor métricas custom de apps.
12. **Alertmanager testing**: Testar rotas de alerta com `amtool` antes de produção.

---

## Práticas ruins ❌

1. **Queries sem filtros**: `{namespace=""}` sem filtros consome muita memória.
2. **Alertas não acionáveis**: Criar alertas para condições informativas sem ação clara.
3. **Retention muito longo**: Manter métricas por meses sem necessidade esgota disco.
4. **Dashboards não documentados**: Criar dashboards sem contexto dificulta manutenção.
5. **Logs não estruturados**: Plain text dificulta queries no Loki.
6. **Silencing sem ticket**: Silenciar alertas sem rastreabilidade.
7. **Não testar alertas**: Não validar alertas em staging pode gerar false positives em produção.
8. **Credentials em alertmanager.yaml**: Expor tokens em ConfigMaps (usar Secrets).
9. **Grafana público**: Expor Grafana sem autenticação.
10. **Ignorar disk pressure**: Não monitorar uso de disco do Prometheus/Loki causa crash.
11. **Scrape interval muito curto**: Scrapes frequentes sobrecarregam targets.
12. **Dashboards duplicados**: Manter múltiplas versões do mesmo dashboard sem organização.

---

## Diagnóstico avançado

### Verificar targets do Prometheus

```bash
kubectl port-forward -n observability svc/kube-prometheus-stack-prometheus 9090:9090
# Acessar http://localhost:9090/targets
```

### Query direta via CLI

```bash
kubectl exec -n observability -it prometheus-kube-prometheus-stack-prometheus-0 -- \
  promtool query instant http://localhost:9090 'up{job="kubernetes-nodes"}'
```

### Verificar regras de alerta ativas

```bash
kubectl get prometheusrules -A
kubectl describe prometheusrule custom-alerts -n observability
```

### Ver alertas ativos

```bash
kubectl port-forward -n observability svc/kube-prometheus-stack-alertmanager 9093:9093
# Acessar http://localhost:9093
```

### Logs do Prometheus Operator

```bash
kubectl logs -n observability -l app.kubernetes.io/name=prometheus-operator --tail=100 -f
```

### Validar config do Alertmanager

```bash
kubectl exec -n observability alertmanager-kube-prometheus-stack-alertmanager-0 -- \
  amtool config show
```

### Testar rota de alerta

```bash
kubectl exec -n observability alertmanager-kube-prometheus-stack-alertmanager-0 -- \
  amtool alert add alertname=Test severity=warning
```

### Verificar datasources no Grafana

```bash
kubectl exec -n observability deployment/grafana -- \
  grafana-cli admin data-sources ls
```

### Consultar Loki via CLI

```bash
kubectl port-forward -n observability svc/loki 3100:3100
curl 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={namespace="apps"}' \
  --data-urlencode 'start=1h' | jq
```

### Ver tamanho do TSDB Prometheus

```bash
kubectl exec -n observability prometheus-kube-prometheus-stack-prometheus-0 -- \
  du -sh /prometheus
```

### Recarregar config do Prometheus (sem restart)

```bash
kubectl exec -n observability prometheus-kube-prometheus-stack-prometheus-0 -- \
  curl -X POST http://localhost:9090/-/reload
```

### Verificar cardinality de métricas

```bash
# Top 10 métricas por cardinalidade
kubectl exec -n observability prometheus-kube-prometheus-stack-prometheus-0 -- \
  promtool tsdb analyze /prometheus | head -20
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Traefik](traefik.md)** | **[Próximo: Secrets →](secrets.md)**
