# Istio — Service Mesh

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Grafana](grafana.md) | [Próximo: Kong →](kong.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Traffic Management](#traffic-management)
- [Security](#security)
- [Observability](#observability)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[Istio](#1-istio)¹** é um **[service mesh](#2-service-mesh)²** que adiciona observabilidade, segurança e controle de tráfego entre microserviços.
- **[Sidecar](#3-sidecar)³**: Proxy Envoy injetado em cada pod intercepta todo tráfego.
- **[Control Plane](#4-control-plane)⁴**: Istiod gerencia configuração e certificados.

## Por que usamos
- **mTLS automático**: Criptografia transparente entre serviços (zero trust).
- **Traffic shaping**: Canary deploys, A/B testing, circuit breakers.
- **Observabilidade**: Métricas L7 (latência, erro rate) sem modificar código.
- **Políticas centralizadas**: AuthorizationPolicy, rate limiting.

## Como está configurado no Raijin (V1)
- **Versão**: Istio 1.21+ (via istioctl)
- **Profile**: `default` (production-ready)
- **Namespace**: `istio-system`
- **Componentes**:
  - **istiod**: Control plane (pilot + citadel + galley)
  - **istio-ingressgateway**: Gateway de entrada (LoadBalancer)
  - **istio-egressgateway**: Gateway de saída (opcional)
- **mTLS**: STRICT mode (forçado em todo mesh)
- **Injection**: Label `istio-injection=enabled` nos namespaces
- **Observabilidade**: Métricas exportadas para Prometheus

## Como operamos

### Habilitar injection em namespace

```bash
# Anotar namespace para auto-injection
kubectl label namespace default istio-injection=enabled

# Verificar
kubectl get namespace -L istio-injection

# Recriar pods existentes (injection só ocorre em pods novos)
kubectl rollout restart deployment -n default
```

### Verificar injection

```bash
# Ver pods com sidecar
kubectl get pods -n default -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}'

# Esperado: nome-pod    app-container istio-proxy

# Ver logs do sidecar
kubectl logs -n default <pod> -c istio-proxy
```

### Criar Gateway

```yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: myapp-gateway
  namespace: default
spec:
  selector:
    istio: ingressgateway  # Usar istio-ingressgateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "myapp.local.io"
```

### Criar VirtualService

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp
  namespace: default
spec:
  hosts:
  - "myapp.local.io"
  gateways:
  - myapp-gateway
  http:
  - route:
    - destination:
        host: myapp-svc
        port:
          number: 8080
```

## Traffic Management

### Canary deployment

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp-canary
spec:
  hosts:
  - myapp-svc
  http:
  - match:
    - headers:
        x-canary:
          exact: "true"
    route:
    - destination:
        host: myapp-svc
        subset: v2
  - route:
    - destination:
        host: myapp-svc
        subset: v1
      weight: 90
    - destination:
        host: myapp-svc
        subset: v2
      weight: 10
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: myapp
spec:
  host: myapp-svc
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
```

### Circuit breaker

```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: myapp-circuit-breaker
spec:
  host: myapp-svc
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 50
        http2MaxRequests: 100
        maxRequestsPerConnection: 2
    outlierDetection:
      consecutiveErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

### Retry policy

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp-retry
spec:
  hosts:
  - myapp-svc
  http:
  - retries:
      attempts: 3
      perTryTimeout: 2s
      retryOn: "5xx,reset,connect-failure,refused-stream"
    route:
    - destination:
        host: myapp-svc
```

## Security

### mTLS STRICT

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT  # Força mTLS em todo mesh
```

### AuthorizationPolicy

```yaml
# Permitir apenas GET/POST no /api
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: api-policy
  namespace: default
spec:
  selector:
    matchLabels:
      app: myapp
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/default/sa/frontend"]
    to:
    - operation:
        methods: ["GET", "POST"]
        paths: ["/api/*"]
```

### RequestAuthentication (JWT)

```yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: jwt-auth
  namespace: default
spec:
  selector:
    matchLabels:
      app: myapp
  jwtRules:
  - issuer: "https://accounts.google.com"
    jwksUri: "https://www.googleapis.com/oauth2/v3/certs"
```

## Observability

### Métricas Istio

```bash
# Port-forward Prometheus
kubectl port-forward -n observability svc/prometheus-kube-prometheus-prometheus 9090:9090

# Queries úteis:
# Request rate
rate(istio_requests_total[5m])

# Latência P95
histogram_quantile(0.95, sum(rate(istio_request_duration_milliseconds_bucket[5m])) by (le, destination_service))

# Error rate
sum(rate(istio_requests_total{response_code=~"5.."}[5m])) by (destination_service)
```

### Kiali (service mesh UI)

```bash
# Instalar Kiali
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.21/samples/addons/kiali.yaml

# Port-forward
kubectl port-forward -n istio-system svc/kiali 20001:20001

# Abrir http://localhost:20001
# Ver topologia do mesh, traffic flow, métricas
```

### Jaeger (distributed tracing)

```bash
# Instalar Jaeger
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.21/samples/addons/jaeger.yaml

# Port-forward
kubectl port-forward -n istio-system svc/tracing 16686:16686

# Abrir http://localhost:16686
```

## Troubleshooting

### Sidecar não injetado

```bash
# Verificar label do namespace
kubectl get namespace default -o yaml | grep istio-injection

# Anotar se ausente
kubectl label namespace default istio-injection=enabled

# Verificar webhook
kubectl get mutatingwebhookconfigurations | grep istio

# Ver logs istiod
kubectl logs -n istio-system -l app=istiod
```

### mTLS falha entre services

```bash
# Verificar modo mTLS
kubectl get peerauthentication -A

# Ver certificados do pod
istioctl proxy-config secret <pod> -n <namespace>

# Ver status mTLS
istioctl authn tls-check <pod>.<namespace>

# Logs do sidecar
kubectl logs <pod> -n <namespace> -c istio-proxy | grep -i tls
```

### Traffic não roteado

```bash
# Verificar VirtualService
kubectl get virtualservice -n <namespace>
kubectl describe virtualservice <name> -n <namespace>

# Verificar DestinationRule
kubectl get destinationrule -n <namespace>

# Ver configuração aplicada no Envoy
istioctl proxy-config route <pod> -n <namespace>
istioctl proxy-config cluster <pod> -n <namespace>

# Logs do sidecar
kubectl logs <pod> -n <namespace> -c istio-proxy --tail=100
```

### Gateway não responde

```bash
# Verificar Gateway
kubectl get gateway -n <namespace>
kubectl describe gateway <name> -n <namespace>

# Verificar istio-ingressgateway
kubectl get svc -n istio-system istio-ingressgateway

# Ver IP externo
kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Testar conectividade
curl -H "Host: myapp.local.io" http://<EXTERNAL-IP>
```

## Glossário

### 1. Istio
**Istio**: Service mesh CNCF; adiciona observabilidade, segurança e controle de tráfego via sidecars Envoy.
- **[istio.io](https://istio.io/)**

### 2. Service Mesh
**Service Mesh**: Camada de infraestrutura que gerencia comunicação entre microserviços (mTLS, traffic shaping, observability).

### 3. Sidecar
**Sidecar**: Container auxiliar (Envoy proxy) injetado em cada pod; intercepta todo tráfego in/out.

### 4. Control Plane
**Control Plane**: Istiod; gerencia configuração, certificados, service discovery.

### 5. Envoy
**Envoy**: Proxy L7 usado como sidecar no Istio; gerencia tráfego e coleta métricas.
- **[envoyproxy.io](https://www.envoyproxy.io/)**

### 6. VirtualService
**VirtualService**: CRD que define regras de roteamento (canary, retry, timeout).

### 7. DestinationRule
**DestinationRule**: CRD que define políticas de tráfego (circuit breaker, load balancing).

### 8. Gateway
**Gateway**: CRD que configura ingress/egress no edge do mesh.

### 9. mTLS
**mTLS**: Mutual TLS; autenticação bidirecional com certificados (client e server).

### 10. PeerAuthentication
**PeerAuthentication**: CRD que configura modo mTLS (STRICT, PERMISSIVE, DISABLE).

---

## Exemplos práticos

### Instalar Istio

```bash
# Download istioctl
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.21.0 sh -
cd istio-1.21.0
export PATH=$PWD/bin:$PATH

# Install profile default
istioctl install --set profile=default -y

# Verificar
kubectl get pods -n istio-system
istioctl verify-install
```

### App completo com Istio

```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
      version: v1
  template:
    metadata:
      labels:
        app: myapp
        version: v1
    spec:
      containers:
      - name: app
        image: myapp:v1
        ports:
        - containerPort: 8080
---
# Service
apiVersion: v1
kind: Service
metadata:
  name: myapp-svc
  namespace: default
spec:
  selector:
    app: myapp
  ports:
  - port: 8080
---
# Gateway
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: myapp-gateway
  namespace: default
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "myapp.local.io"
---
# VirtualService
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp
  namespace: default
spec:
  hosts:
  - "myapp.local.io"
  gateways:
  - myapp-gateway
  http:
  - route:
    - destination:
        host: myapp-svc
        port:
          number: 8080
```

### Timeout e retry

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp-resilience
spec:
  hosts:
  - myapp-svc
  http:
  - timeout: 10s
    retries:
      attempts: 3
      perTryTimeout: 2s
      retryOn: "5xx,reset,connect-failure"
    route:
    - destination:
        host: myapp-svc
```

### Rate limiting

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: rate-limit
  namespace: istio-system
spec:
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.local_ratelimit
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
          stat_prefix: http_local_rate_limiter
          token_bucket:
            max_tokens: 100
            tokens_per_fill: 100
            fill_interval: 60s
```

---

## Boas práticas ✅

1. **mTLS STRICT**: Forçar em todo mesh (PeerAuthentication).
2. **Namespace injection**: Label `istio-injection=enabled` por namespace.
3. **Gateway dedicado**: Um Gateway por domínio/aplicação.
4. **DestinationRule para circuit breaker**: Proteger backends.
5. **Retry com backoff**: Evitar cascata de falhas.
6. **Timeout agressivo**: 10s max (evitar requests lentos).
7. **Canary com header**: Testar antes de weight-based.
8. **AuthorizationPolicy default-deny**: Whitelist explícito.
9. **Monitorar Envoy metrics**: `istio_requests_total`, `istio_request_duration_milliseconds`.
10. **Kiali para debug**: Visualizar topologia e traffic flow.
11. **Jaeger para tracing**: Identificar bottlenecks.
12. **Resource limits em sidecars**: Evitar OOMKilled.
13. **Upgrade incremental**: Canary do próprio Istio.
14. **Logs do sidecar**: Enviar para Loki.
15. **Documentar políticas**: Justificar cada AuthorizationPolicy.

---

## Práticas ruins ❌

1. **mTLS PERMISSIVE em prod**: Permite plaintext (inseguro).
2. **Injection manual**: Usar `istioctl kube-inject` (não escala).
3. **Gateway genérico**: Um Gateway para todas apps (dificulta debug).
4. **Sem circuit breaker**: Cascata de falhas derruba mesh.
5. **Retry infinito**: Amplifica falhas (max 3 attempts).
6. **Timeout gigante**: Requests travados por minutos.
7. **Canary sem métricas**: Deploy v2 quebrado sem detectar.
8. **AuthorizationPolicy allow-all**: Não usar service mesh.
9. **Não monitorar Envoy**: Descobrir problema tarde.
10. **Sem Kiali/Jaeger**: Debug às cegas.
11. **Sidecar sem limites**: Consome toda RAM do pod.
12. **Upgrade sem teste**: Quebrar mesh em produção.
13. **Logs do sidecar ignorados**: Perder context de falhas.
14. **VirtualService complexo**: 100+ rules em um VS (dividir).
15. **Istio em clusters pequenos**: Overhead para <10 services.

---

## Diagnóstico avançado

### Ver configuração Envoy

```bash
# Listar listeners, routes, clusters, endpoints
istioctl proxy-config listener <pod> -n <namespace>
istioctl proxy-config route <pod> -n <namespace>
istioctl proxy-config cluster <pod> -n <namespace>
istioctl proxy-config endpoint <pod> -n <namespace>

# Ver configuração completa
istioctl proxy-config all <pod> -n <namespace> -o json
```

### Analisar configuração

```bash
# Validar CRDs
istioctl analyze -n <namespace>

# Ver status do mesh
istioctl proxy-status

# Ver versão dos sidecars
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="istio-proxy")].image}{"\n"}{end}'
```

### Debug mTLS

```bash
# Ver certificados
istioctl proxy-config secret <pod> -n <namespace>

# Verificar mTLS entre services
istioctl authn tls-check <pod>.<namespace> <service>.<namespace>.svc.cluster.local

# Ver CA root
kubectl get secret -n istio-system istio-ca-secret -o jsonpath='{.data.ca-cert\.pem}' | base64 -d | openssl x509 -text
```

### Logs detalhados sidecar

```bash
# Habilitar debug logs
istioctl proxy-config log <pod> -n <namespace> --level debug

# Ver logs
kubectl logs <pod> -n <namespace> -c istio-proxy --tail=100 -f

# Filtrar por componente
kubectl logs <pod> -n <namespace> -c istio-proxy | grep -E "router|upstream"
```

### Métricas Envoy

```bash
# Port-forward Envoy admin
kubectl port-forward <pod> -n <namespace> 15000:15000

# Stats
curl http://localhost:15000/stats/prometheus

# Config dump
curl http://localhost:15000/config_dump | jq

# Clusters health
curl http://localhost:15000/clusters
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Grafana](grafana.md)** | **[Próximo: Kong →](kong.md)**
