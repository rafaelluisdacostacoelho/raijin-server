# Kong — API Gateway

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Istio](istio.md) | [Próximo: Argo →](argo.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Plugins](#plugins)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)

---

## O que é
- **[Kong](#1-kong)¹** é um **[API Gateway](#2-api-gateway)²** cloud-native baseado em Nginx/OpenResty.
- **[Plugins](#3-plugin)³**: Rate limiting, autenticação, logging, transformações (80+ plugins oficiais).
- **[Declarative config](#4-declarative-config)⁴**: Configuração via CRDs Kubernetes (KongIngress, KongPlugin).

## Por que usamos
- **Alternativa ao Istio**: Mais leve para cenários sem service mesh completo.
- **Plugins prontos**: Rate limiting, JWT auth, CORS, request transformation.
- **DB-less mode**: Configuração via ConfigMaps/CRDs (sem PostgreSQL).
- **Performance**: Baseado em Nginx (alta throughput, baixa latência).

## Como está configurado no Raijin (V1)
- **Versão**: Kong 3.5+ (Helm chart `kong/kong`)
- **Namespace**: `kong`
- **Modo**: **DB-less** (sem banco de dados, config via CRDs)
- **Ingress Controller**: Kong Ingress Controller (KIC)
- **Acesso**: LoadBalancer via MetalLB (porta 80/443)
- **Plugins habilitados**: rate-limiting, cors, jwt, prometheus

## Como operamos

### Criar Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: default
  annotations:
    konghq.com/strip-path: "true"
spec:
  ingressClassName: kong
  rules:
  - host: myapp.local.io
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: myapp-svc
            port:
              number: 8080
```

### Aplicar plugin

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: rate-limit
  namespace: default
config:
  minute: 100
  policy: local
plugin: rate-limiting
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: default
  annotations:
    konghq.com/plugins: rate-limit
spec:
  # ... (igual anterior)
```

### Ver configuração

```bash
# Pods Kong
kubectl get pods -n kong

# Services
kubectl get svc -n kong

# Ingresses
kubectl get ingress -A

# Plugins aplicados
kubectl get kongplugins -A
```

## Plugins

### Rate Limiting

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: rate-limit-strict
config:
  minute: 60
  hour: 1000
  policy: local
  fault_tolerant: true
plugin: rate-limiting
```

### JWT Authentication

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: jwt-auth
config:
  claims_to_verify:
  - exp
  key_claim_name: iss
plugin: jwt
```

### CORS

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: cors
config:
  origins:
  - "https://app.local.io"
  methods:
  - GET
  - POST
  headers:
  - Authorization
  - Content-Type
  exposed_headers:
  - X-Auth-Token
  credentials: true
  max_age: 3600
plugin: cors
```

### Request Transformer

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: add-headers
config:
  add:
    headers:
    - "X-Server: Kong"
    - "X-Environment: production"
plugin: request-transformer
```

## Troubleshooting

### Ingress não responde

```bash
# Verificar Kong proxy
kubectl get svc -n kong kong-proxy
kubectl get endpoints -n kong kong-proxy

# Testar conectividade
KONG_PROXY_IP=$(kubectl get svc -n kong kong-proxy -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -H "Host: myapp.local.io" http://$KONG_PROXY_IP/api

# Logs Kong
kubectl logs -n kong -l app.kubernetes.io/component=app
```

### Plugin não aplica

```bash
# Verificar KongPlugin
kubectl get kongplugin <name> -n <namespace> -o yaml

# Ver annotation no Ingress
kubectl get ingress <name> -n <namespace> -o yaml | grep konghq.com/plugins

# Logs do controller
kubectl logs -n kong -l app.kubernetes.io/name=ingress-kong
```

### Rate limit não funciona

```bash
# Testar rate limit
for i in {1..150}; do curl -s -o /dev/null -w "%{http_code}\n" http://myapp.local.io/api; done

# Esperado: primeiros 100 retornam 200, resto 429

# Ver config do plugin
kubectl get kongplugin rate-limit -o yaml
```

## Glossário

### 1. Kong
**Kong**: API Gateway open-source baseado em Nginx/OpenResty; gerencia tráfego, segurança, observabilidade.
- **[konghq.com](https://konghq.com/)**

### 2. API Gateway
**API Gateway**: Proxy reverso que centraliza roteamento, autenticação, rate limiting de APIs.

### 3. Plugin
**Plugin**: Módulo Kong que adiciona funcionalidade (rate-limit, JWT, logging, etc).

### 4. Declarative Config
**Declarative Config**: Modo DB-less do Kong; configuração via YAML/CRDs (sem PostgreSQL).

### 5. Ingress Controller
**Ingress Controller**: Componente que converte Ingress K8s em configuração Kong.

### 6. KongPlugin
**KongPlugin**: CRD para configurar plugins Kong.

### 7. KongIngress
**KongIngress**: CRD para configurações avançadas de proxy (timeouts, retries).

### 8. Upstream
**Upstream**: Backend service que Kong roteia tráfego (Service K8s).

### 9. Route
**Route**: Regra de roteamento (path, host, method) → Upstream.

### 10. Consumer
**Consumer**: Entidade autenticada no Kong (usuário ou aplicação com credenciais).

---

## Exemplos práticos

### Instalar Kong

```bash
helm repo add kong https://charts.konghq.com
helm repo update

cat << EOF > kong-values.yaml
ingressController:
  enabled: true
  installCRDs: true

env:
  database: "off"  # DB-less mode
  nginx_worker_processes: "2"

proxy:
  type: LoadBalancer
  annotations:
    metallb.universe.tf/loadBalancerIPs: 192.168.1.245

admin:
  enabled: false  # Não expor Admin API

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2
    memory: 2Gi
EOF

helm install kong kong/kong \
  -n kong \
  --create-namespace \
  -f kong-values.yaml
```

### Ingress completo

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: default
  annotations:
    konghq.com/strip-path: "true"
    konghq.com/plugins: rate-limit,cors,jwt-auth
    konghq.com/protocols: "https"
    konghq.com/https-redirect-status-code: "301"
spec:
  ingressClassName: kong
  tls:
  - hosts:
    - myapp.local.io
    secretName: myapp-tls
  rules:
  - host: myapp.local.io
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: myapp-svc
            port:
              number: 8080
```

### Multi-plugin stack

```yaml
# Rate limiting
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: rate-limit
config:
  minute: 100
plugin: rate-limiting
---
# JWT
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: jwt-auth
plugin: jwt
---
# CORS
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: cors
config:
  origins: ["*"]
  credentials: true
plugin: cors
---
# Ingress com todos plugins
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  annotations:
    konghq.com/plugins: rate-limit,jwt-auth,cors
spec:
  ingressClassName: kong
  # ...
```

---

## Boas práticas ✅

1. **DB-less mode**: Usar `database: off` (sem PostgreSQL).
2. **LoadBalancer via MetalLB**: IP fixo para Kong proxy.
3. **TLS via cert-manager**: Certificados automáticos.
4. **Rate limiting padrão**: Aplicar em todos Ingresses.
5. **JWT para autenticação**: Evitar API keys hardcoded.
6. **CORS configurado**: Evitar erros em SPAs.
7. **Logs estruturados**: Plugin `file-log` ou `http-log`.
8. **Métricas Prometheus**: Plugin `prometheus` habilitado.
9. **Health checks**: `/status` endpoint do Kong.
10. **Resource limits**: Evitar OOMKilled.
11. **Versionamento de config**: CRDs no Git.
12. **Não expor Admin API**: `admin.enabled: false`.
13. **Namespace dedicado**: Kong em namespace `kong`.
14. **Timeout adequado**: 60s default (ajustar para APIs lentas).
15. **Retry policy**: Configurar via KongIngress.

---

## Práticas ruins ❌

1. **Usar PostgreSQL**: Adiciona complexidade desnecessária.
2. **Admin API público**: Expor porta 8001 sem autenticação.
3. **Sem rate limiting**: APIs abertas para abuse.
4. **API keys em plaintext**: Usar Secrets K8s.
5. **CORS allow-all**: `origins: ["*"]` com `credentials: true`.
6. **Logs não centralizados**: Debugar via `kubectl logs`.
7. **Sem métricas**: Não monitorar latência/error rate.
8. **Health checks desabilitados**: Kong down sem detectar.
9. **Sem resource limits**: Kong consumir toda RAM.
10. **Config manual**: Editar via Admin API (não declarativo).
11. **Não versionar CRDs**: Perder configuração em falhas.
12. **Timeout muito curto**: APIs lentas retornando 504.
13. **Múltiplos Ingress Controllers**: Conflito com Traefik/Nginx.
14. **Plugins em cascata**: 10+ plugins causam latência.
15. **Não testar plugins**: Deploy plugin quebrado em produção.

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Istio](istio.md)** | **[Próximo: Argo →](argo.md)**
