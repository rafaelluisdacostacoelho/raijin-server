# Grafana — Visualização e Dashboards

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Prometheus](prometheus.md) | [Próximo: Istio →](istio.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Dashboards](#dashboards)
- [Alerting](#alerting)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[Grafana](#1-grafana)¹** é a plataforma open-source para visualização de métricas e logs.
- **[Datasources](#2-datasource)²**: Prometheus, Loki, InfluxDB, Elasticsearch, MySQL, etc.
- **[Dashboards](#3-dashboard)³**: Painéis interativos com gráficos, tabelas, alertas.

## Por que usamos
- **Visualização unificada**: Métricas (Prometheus) + Logs (Loki) em um único painel.
- **Dashboards prontos**: 1000+ dashboards na [grafana.com](https://grafana.com/grafana/dashboards/).
- **Alerting integrado**: Alertas visuais com notificações (Slack, email, webhook).
- **Multi-tenancy**: Separação por organizações e permissões (Admin, Editor, Viewer).

## Como está configurado no Raijin (V1)
- **Versão**: Grafana 10.3+ (via kube-prometheus-stack Helm chart)
- **Namespace**: `observability`
- **Acesso**: 
  - **URL**: `http://grafana.observability.svc:3000` (interno)
  - **Ingress**: `https://grafana.local.io` (via Traefik)
  - **Credenciais padrão**: `admin / admin123` (mudar em produção!)
- **Datasources pré-configurados**:
  - **Prometheus**: `http://prometheus-kube-prometheus-prometheus:9090`
  - **Loki**: `http://loki.observability.svc:3100`
- **Dashboards pré-instalados**:
  - Kubernetes Cluster Monitoring
  - Node Exporter Full
  - Traefik
  - cert-manager
- **Provisioning**: Dashboards e datasources via ConfigMaps

## Como operamos

### Acessar Grafana

```bash
# Port-forward
kubectl port-forward -n observability svc/prometheus-grafana 3000:80

# Abrir http://localhost:3000
# Login: admin / admin123

# Ou via Ingress (se configurado)
curl https://grafana.local.io
```

### Criar dashboard

```bash
# Grafana UI:
# 1. + (menu) → Create → Dashboard
# 2. Add Panel → escolher Datasource (Prometheus/Loki)
# 3. Escrever query PromQL/LogQL
# 4. Configurar visualização (Time series, Gauge, Table)
# 5. Save dashboard
```

### Importar dashboard

```bash
# Grafana UI:
# Dashboards → Import → inserir ID do dashboard

# Dashboards úteis:
# - 315: Kubernetes cluster monitoring
# - 1860: Node Exporter Full
# - 12113: Traefik 2
# - 11455: cert-manager
```

### Provisionar dashboard via ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-dashboard
  namespace: observability
  labels:
    grafana_dashboard: "1"
data:
  my-dashboard.json: |
    {
      "dashboard": {
        "title": "My App",
        "panels": [...],
        "uid": "myapp"
      }
    }
```

## Dashboards

### Kubernetes Cluster

```json
{
  "title": "Kubernetes Cluster",
  "panels": [
    {
      "title": "CPU Usage",
      "targets": [{
        "expr": "sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)",
        "datasource": "Prometheus"
      }]
    },
    {
      "title": "Memory Usage",
      "targets": [{
        "expr": "sum(container_memory_working_set_bytes) by (pod) / 1024 / 1024",
        "datasource": "Prometheus"
      }]
    }
  ]
}
```

### Logs (Loki)

```json
{
  "title": "Application Logs",
  "panels": [
    {
      "title": "Error Logs",
      "targets": [{
        "expr": "{namespace=\"traefik\"} |= \"error\"",
        "datasource": "Loki"
      }],
      "type": "logs"
    },
    {
      "title": "Log Rate",
      "targets": [{
        "expr": "sum(rate({namespace=\"traefik\"}[5m])) by (pod)",
        "datasource": "Loki"
      }]
    }
  ]
}
```

### Variables

```json
{
  "templating": {
    "list": [
      {
        "name": "namespace",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(kube_pod_info, namespace)"
      },
      {
        "name": "pod",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(kube_pod_info{namespace=\"$namespace\"}, pod)"
      }
    ]
  }
}
```

## Alerting

### Configurar notificação

```yaml
# Grafana UI: Alerting → Contact points → New contact point

# Slack
apiVersion: v1
kind: Secret
metadata:
  name: grafana-slack-webhook
  namespace: observability
stringData:
  url: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

### Criar alerta

```yaml
# Grafana UI: Alerting → Alert rules → New alert rule

# Exemplo: Alta taxa de erro
{
  "name": "High Error Rate",
  "condition": "rate({namespace=\"traefik\"} |= \"error\" [5m]) > 10",
  "for": "5m",
  "annotations": {
    "summary": "Alta taxa de erros no Traefik"
  },
  "labels": {
    "severity": "warning"
  },
  "notifications": ["slack-channel"]
}
```

## Troubleshooting

### Grafana não inicia

```bash
# Ver logs
kubectl logs -n observability <grafana-pod>

# Verificar recursos
kubectl describe pod -n observability <grafana-pod>

# Ver eventos
kubectl get events -n observability --sort-by='.lastTimestamp' | grep grafana
```

### Datasource não conecta

```bash
# Testar conectividade Grafana → Prometheus
kubectl exec -n observability <grafana-pod> -- wget -qO- http://prometheus-kube-prometheus-prometheus:9090/-/healthy

# Testar Grafana → Loki
kubectl exec -n observability <grafana-pod> -- wget -qO- http://loki.observability.svc:3100/ready

# Ver configuração datasources
kubectl get cm -n observability | grep datasource
kubectl get cm grafana-datasources -n observability -o yaml
```

### Dashboard não carrega

```bash
# Ver logs Grafana
kubectl logs -n observability <grafana-pod> | grep -i "dashboard\|error"

# Verificar provisioning
kubectl exec -n observability <grafana-pod> -- ls /etc/grafana/provisioning/dashboards/

# Validar JSON do dashboard
jq . dashboard.json  # Verificar sintaxe
```

### Query sem dados

```bash
# Testar query no Prometheus/Loki diretamente
curl 'http://prometheus.observability.svc:9090/api/v1/query?query=up'

# Verificar time range
# Se range for muito antigo, pode não ter dados

# Ver datasource configurado no painel
# Edit Panel → Query → Datasource
```

## Glossário

### 1. Grafana
**Grafana**: Plataforma de visualização e observabilidade; cria dashboards a partir de múltiplos datasources.
- **[grafana.com](https://grafana.com/)**

### 2. Datasource
**Datasource**: Fonte de dados conectada ao Grafana (Prometheus, Loki, MySQL, etc).

### 3. Dashboard
**Dashboard**: Painel com múltiplos gráficos/painéis organizados para monitoramento.

### 4. Panel
**Panel**: Widget individual em dashboard (gráfico, gauge, table, logs).

### 5. Query
**Query**: Consulta a datasource (PromQL para Prometheus, LogQL para Loki).

### 6. Variable
**Variable**: Parâmetro dinâmico em dashboard (ex.: `$namespace`, `$pod`).

### 7. Annotation
**Annotation**: Marcador visual em gráfico (ex.: deploy, incident).

### 8. Provisioning
**Provisioning**: Configuração automatizada de datasources/dashboards via arquivos.

### 9. Organization
**Organization**: Tenant isolado no Grafana (usuários, dashboards, datasources).

### 10. Alert Rule
**Alert Rule**: Regra de alerta baseada em query (envia notificação quando condição é atendida).

---

## Exemplos práticos

### Instalar Grafana standalone

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

cat << EOF > grafana-values.yaml
adminPassword: admin123

datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus-kube-prometheus-prometheus:9090
      isDefault: true
    - name: Loki
      type: loki
      url: http://loki.observability.svc:3100

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
    - name: 'default'
      folder: 'General'
      type: file
      options:
        path: /var/lib/grafana/dashboards/default

dashboards:
  default:
    kubernetes-cluster:
      gnetId: 315
      datasource: Prometheus
    node-exporter:
      gnetId: 1860
      datasource: Prometheus

ingress:
  enabled: true
  hosts:
  - grafana.local.io
  tls:
  - secretName: grafana-tls
    hosts:
    - grafana.local.io

persistence:
  enabled: true
  size: 10Gi
EOF

helm install grafana grafana/grafana \
  -n observability \
  -f grafana-values.yaml
```

### Dashboard customizado

```json
{
  "dashboard": {
    "title": "My Application",
    "uid": "myapp",
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Requests per Second",
        "type": "graph",
        "datasource": "Prometheus",
        "targets": [
          {
            "expr": "sum(rate(http_requests_total{app=\"myapp\"}[5m]))",
            "legendFormat": "RPS"
          }
        ],
        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}
      },
      {
        "id": 2,
        "title": "Error Rate",
        "type": "stat",
        "datasource": "Prometheus",
        "targets": [
          {
            "expr": "100 * sum(rate(http_requests_total{app=\"myapp\",status=~\"5..\"}[5m])) / sum(rate(http_requests_total{app=\"myapp\"}[5m]))"
          }
        ],
        "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "steps": [
                {"value": 0, "color": "green"},
                {"value": 1, "color": "yellow"},
                {"value": 5, "color": "red"}
              ]
            },
            "unit": "percent"
          }
        }
      },
      {
        "id": 3,
        "title": "Error Logs",
        "type": "logs",
        "datasource": "Loki",
        "targets": [
          {
            "expr": "{app=\"myapp\"} |= \"error\""
          }
        ],
        "gridPos": {"x": 0, "y": 8, "w": 24, "h": 8}
      }
    ],
    "time": {"from": "now-1h", "to": "now"},
    "refresh": "30s"
  }
}
```

### Variables avançadas

```json
{
  "templating": {
    "list": [
      {
        "name": "datasource",
        "type": "datasource",
        "query": "prometheus",
        "current": {"text": "Prometheus", "value": "Prometheus"}
      },
      {
        "name": "namespace",
        "type": "query",
        "datasource": "$datasource",
        "query": "label_values(kube_pod_info, namespace)",
        "multi": true,
        "includeAll": true
      },
      {
        "name": "pod",
        "type": "query",
        "datasource": "$datasource",
        "query": "label_values(kube_pod_info{namespace=~\"$namespace\"}, pod)",
        "multi": false
      },
      {
        "name": "interval",
        "type": "interval",
        "query": "1m,5m,10m,30m,1h",
        "current": {"text": "5m", "value": "5m"}
      }
    ]
  }
}
```

### Alert rule completo

```json
{
  "alert": {
    "name": "High CPU Usage",
    "condition": [
      {
        "query": {
          "model": {
            "expr": "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "datasource": "Prometheus"
          }
        },
        "reducer": {"type": "last"},
        "evaluator": {"type": "gt", "params": [80]}
      }
    ],
    "executionErrorState": "alerting",
    "for": "5m",
    "frequency": "1m",
    "handler": 1,
    "message": "CPU usage is above 80%",
    "name": "High CPU Usage",
    "noDataState": "no_data",
    "notifications": [
      {"uid": "slack-notification"}
    ]
  }
}
```

---

## Boas práticas ✅

1. **Mudar senha padrão**: `admin/admin123` → senha forte.
2. **Datasources provisionados**: Via ConfigMap, não manual.
3. **Dashboards em Git**: Versionar JSON dos dashboards.
4. **Variables para reuso**: Criar dashboards genéricos com `$namespace`, `$pod`.
5. **Annotations para eventos**: Marcar deploys, incidents em gráficos.
6. **Folders organizados**: Agrupar dashboards por componente (Network, Storage, Apps).
7. **Permissões adequadas**: Viewer para devs, Editor para SRE, Admin para infra.
8. **Refresh interval**: 30s padrão (não 5s para economizar recursos).
9. **Time range adequado**: Último 1h padrão (não 24h).
10. **Alertas com thresholds**: Usar cores (verde/amarelo/vermelho).
11. **Logs e métricas juntos**: Combinar Prometheus + Loki em um dashboard.
12. **Dashboards da comunidade**: Importar da [grafana.com/dashboards](https://grafana.com/grafana/dashboards/).
13. **Backup de dashboards**: Exportar JSON periodicamente.
14. **HTTPS via Ingress**: Não expor Grafana em HTTP.
15. **Limitar query range**: `max_query_length` para evitar queries gigantes.

---

## Práticas ruins ❌

1. **Senha padrão em produção**: Manter `admin/admin123`.
2. **Datasources manuais**: Configurar via UI (perdido em redeploy).
3. **Dashboards não versionados**: Perder customizações em falha.
4. **Sem variables**: Criar 10 dashboards idênticos para cada namespace.
5. **Refresh 5s**: Sobrecarregar Prometheus/Loki.
6. **Time range 7d em default**: Queries lentas e custosas.
7. **Admin para todos**: Usuários deletarem dashboards acidentalmente.
8. **HTTP sem autenticação**: Expor Grafana publicamente.
9. **Query complexos direto no painel**: Usar recording rules no Prometheus.
10. **Sem organização**: 100 dashboards na pasta raiz.
11. **Alertas demais**: Alert fatigue; focar em SLOs críticos.
12. **Sem anotações**: Não documentar o que cada painel mostra.
13. **Ignorar logs Grafana**: Não debugar erros de datasource.
14. **Dashboards gigantes**: 50+ painéis em um dashboard (lento).
15. **Não testar alertas**: Descobrir que notificação não funciona em incident.

---

## Diagnóstico avançado

### Debug de datasources

```bash
# Listar datasources via API
kubectl port-forward -n observability svc/prometheus-grafana 3000:80
curl -u admin:admin123 http://localhost:3000/api/datasources

# Testar health de datasource
curl -u admin:admin123 http://localhost:3000/api/datasources/1/health

# Ver configuração
kubectl get cm -n observability grafana-datasources -o yaml
```

### Exportar dashboards

```bash
# Via API
curl -u admin:admin123 http://localhost:3000/api/dashboards/uid/myapp | jq .dashboard > myapp-dashboard.json

# Listar todos dashboards
curl -u admin:admin123 http://localhost:3000/api/search | jq

# Backup de todos
for uid in $(curl -s -u admin:admin123 http://localhost:3000/api/search | jq -r '.[].uid'); do
  curl -s -u admin:admin123 "http://localhost:3000/api/dashboards/uid/$uid" | jq .dashboard > "dashboard-$uid.json"
done
```

### Verificar provisioning

```bash
# Listar arquivos provisionados
kubectl exec -n observability <grafana-pod> -- ls -la /etc/grafana/provisioning/datasources/
kubectl exec -n observability <grafana-pod> -- ls -la /etc/grafana/provisioning/dashboards/

# Ver conteúdo
kubectl exec -n observability <grafana-pod> -- cat /etc/grafana/provisioning/datasources/datasources.yaml
```

### Métricas Grafana

```bash
# Port-forward
kubectl port-forward -n observability svc/prometheus-grafana 3000:80

# Métricas internas
curl http://localhost:3000/metrics | grep grafana_

# Dashboards carregados
grafana_dashboard_get_total

# Queries executadas
grafana_datasource_request_total
```

### Logs detalhados

```bash
# Habilitar debug logs
kubectl set env -n observability deployment/prometheus-grafana GF_LOG_LEVEL=debug

# Ver logs
kubectl logs -n observability <grafana-pod> --tail=100 -f

# Filtrar erros
kubectl logs -n observability <grafana-pod> | grep -E "error|ERROR|fatal"
```

### Reset senha admin

```bash
# Via CLI no pod
kubectl exec -n observability <grafana-pod> -- grafana-cli admin reset-admin-password newpassword123

# Ou editar secret
kubectl get secret -n observability prometheus-grafana -o json | \
  jq '.data["admin-password"]="bmV3cGFzc3dvcmQxMjM="' | \
  kubectl apply -f -
# (bmV3cGFzc3dvcmQxMjM= é base64 de "newpassword123")
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Prometheus](prometheus.md)** | **[Próximo: Istio →](istio.md)**
