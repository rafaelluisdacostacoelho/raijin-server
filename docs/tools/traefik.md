# Traefik (Ingress Controller L7)

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Cert-Manager](cert-manager.md) | [Próximo: Observability →](observability.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Manutenção](#manutenção-e-monitoramento)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **Ingress¹ Controller** L7 que expõe os serviços do cluster via HTTP/HTTPS.
- Opera no namespace `traefik` com Service **LoadBalancer³**/NodePort conforme ambiente.
- Roteamento dinâmico baseado em host/path para backends do Kubernetes.

## Por que usamos
- Configuração simples via recursos **Ingress** padrão (sem CRDs⁴ proprietários obrigatórios).
- Integração direta com Cert-Manager para HTTP-01 (Let's Encrypt).
- Suporte a **middlewares⁵** (rate limit, auth, headers) sem complexidade extra.
- Dashboard integrado para observabilidade de rotas.

## Como está configurado no Raijin (V1)
- Namespace: `traefik`.
- Exposição: Service LoadBalancer ou NodePort (dependendo do ambiente) recebendo 80/443.
- IngressClass: `traefik` (padrão para os manifests gerados pelo projeto).
- TLS: Cert-Manager emite certificados via HTTP-01; Traefik responde aos desafios.
- Middlewares: mantemos o mínimo; uso opcional para auth/rate-limit quando necessário.

## O que o Traefik resolve na nossa arquitetura
- Publica os serviços HTTP/HTTPS do cluster de forma padronizada (Ingress).
- Encaminha o desafio ACME HTTP-01 para Cert-Manager emitir certificados.
- Simplifica roteamento por host/path, sem exigir CRDs proprietários.
- Permite adicionar middlewares (auth/rate-limit) quando preciso, sem acoplar nas apps.

## Manutenção e monitoramento
- Saúde: `kubectl get pods -n traefik` e `kubectl logs -n traefik -l app.kubernetes.io/name=traefik`.
- Service/Endpoints: `kubectl get svc,ep -n traefik` para garantir que há backends prontos.
- Renovação TLS: verificar eventos do Cert-Manager e validade dos Secrets `<nome>-tls`.
- Atualizações: alinhar a versão do chart/manifests com o restante do stack; validar em staging.

## Como operamos
- Health: `kubectl get pods -n traefik` e `kubectl logs -n traefik -l app.kubernetes.io/name=traefik`.
- Ingress padrão: defina `ingressClassName: traefik` e a annotation `cert-manager.io/cluster-issuer: "letsencrypt-prod"` quando precisar de TLS.
- Middlewares e outros recursos CRD podem ser usados, mas mantemos o mínimo para reduzir drift.

## TLS com Cert-Manager
- Traefik responde o desafio HTTP-01 para o Cert-Manager.
- Requisitos: DNS apontando para o IP de entrada e annotation `cert-manager.io/cluster-issuer` no Ingress.

## Troubleshooting
- Ver Ingress: `kubectl describe ingress <nome> -n <ns>`.
- Ver pods/logs do Traefik: `kubectl logs -n traefik -l app.kubernetes.io/name=traefik`.
- Conferir Service/Endpoints: `kubectl get svc,ep -n traefik`.
- Se TLS falhar, checar challenges em cert-manager (veja o guia de Cert-Manager).

## Links úteis
- https://doc.traefik.io/traefik/

---

## Glossário

1. **Ingress**: Recurso Kubernetes que define regras de roteamento HTTP/HTTPS para Services.
2. **L7** (Layer 7): Camada de aplicação do modelo OSI (HTTP, HTTPS, routing por host/path).
3. **LoadBalancer**: Tipo de Service que provisiona IP externo (via MetalLB no bare metal ou cloud provider).
4. **CRD** (Custom Resource Definition): Extensão da API Kubernetes; Traefik suporta IngressRoute mas não é obrigatório.
5. **Middleware**: Recurso do Traefik para transformar requisições (auth, rate limit, headers, redirect).
6. **NodePort**: Tipo de Service que expõe porta em todos os nodes (ex.: 30080, 30443).
7. **IngressClass**: Define qual controller processa o Ingress (`traefik`, `nginx`, etc).
8. **Backend**: Service/Pod que recebe tráfego roteado pelo Ingress.
9. **EntryPoint**: Ponto de entrada do Traefik (web:80, websecure:443).
10. **TLS Passthrough**: Modo onde Traefik não termina TLS, encaminha criptografado para backend.

---

## Exemplos práticos

### Ingress básico HTTP

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: apps
spec:
  ingressClassName: traefik
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp
            port:
              number: 80
```

### Ingress com TLS automático (Cert-Manager)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: apps
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - myapp.example.com
    secretName: myapp-tls
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp
            port:
              number: 80
```

### Middleware: Rate Limiting

```yaml
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: rate-limit
  namespace: apps
spec:
  rateLimit:
    average: 100
    burst: 50
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: apps
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: apps-rate-limit@kubernetescrd
spec:
  ingressClassName: traefik
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp
            port:
              number: 80
```

### Middleware: Basic Auth

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: auth-secret
  namespace: apps
data:
  users: YWRtaW46JGFwcjEkSDY1dnBkJC56QjJTdVZNb0FRRGRwWlNlN2d6MDEKCg==  # admin:password
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: basic-auth
  namespace: apps
spec:
  basicAuth:
    secret: auth-secret
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: protected-app
  namespace: apps
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: apps-basic-auth@kubernetescrd
spec:
  ingressClassName: traefik
  rules:
  - host: protected.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: protected-app
            port:
              number: 80
```

---

## Boas práticas ✅

1. **IngressClass explícita**: Sempre definir `ingressClassName: traefik` para evitar ambiguidade.
2. **TLS por padrão**: Usar Cert-Manager + TLS para todos os Ingresses públicos.
3. **Middlewares modulares**: Criar middlewares reutilizáveis (auth, rate-limit) por namespace.
4. **Health checks**: Validar backends com readiness probes antes de expor via Ingress.
5. **DNS antes do Ingress**: Garantir que DNS aponta para LoadBalancer/NodePort antes de aplicar.
6. **Rate limiting**: Proteger APIs públicas com rate limit para evitar abuse.
7. **Logs estruturados**: Habilitar access logs do Traefik em formato JSON para análise.
8. **Dashboard seguro**: Acessar dashboard via port-forward ou VPN (nunca expor publicamente sem auth).
9. **Namespaces isolados**: Manter Ingresses e middlewares no mesmo namespace da app.
10. **Monitorar métricas**: Integrar Traefik com Prometheus para observabilidade.

---

## Práticas ruins ❌

1. **Sem IngressClass**: Omitir `ingressClassName` pode causar conflito se houver múltiplos controllers.
2. **HTTP sem redirect**: Expor apps sensíveis em HTTP puro sem redirect para HTTPS.
3. **Middlewares globais**: Aplicar middleware de auth em todos os Ingresses sem necessidade.
4. **Dashboard público**: Expor dashboard Traefik sem autenticação.
5. **Backend sem readiness**: Rotear tráfego para pods não prontos causa 503.
6. **DNS incorreto**: Aplicar Ingress antes de DNS propagar causa falha TLS.
7. **Middlewares órfãos**: Criar middlewares sem documentar uso.
8. **TLS self-signed**: Usar certificados auto-assinados em produção.
9. **Portas hardcoded**: Não usar NodePort consistente entre ambientes.
10. **Logs ignorados**: Não monitorar access logs do Traefik pode esconder ataques.

---

## Diagnóstico avançado

### Verificar status do Traefik

```bash
kubectl get pods -n traefik
kubectl logs -n traefik -l app.kubernetes.io/name=traefik --tail=100 -f
```

### Ver Service e Endpoints

```bash
kubectl get svc,ep -n traefik
```

### Inspecionar Ingress

```bash
kubectl describe ingress myapp -n apps
kubectl get ingress myapp -n apps -o yaml
```

### Testar conectividade externa

```bash
curl -v http://myapp.example.com
curl -v https://myapp.example.com
```

### Verificar TLS handshake

```bash
openssl s_client -connect myapp.example.com:443 -servername myapp.example.com < /dev/null
```

### Port-forward para dashboard

```bash
kubectl port-forward -n traefik deployment/traefik 9000:9000
# Acessar http://localhost:9000/dashboard/
```

### Verificar middlewares ativos

```bash
kubectl get middlewares -A
kubectl describe middleware rate-limit -n apps
```

### Logs com filtro de erros

```bash
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep -i error
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep -i 5xx
```

### Testar backend diretamente (bypass Ingress)

```bash
kubectl port-forward -n apps svc/myapp 8080:80
curl http://localhost:8080
```

### Verificar rotas configuradas

```bash
kubectl exec -n traefik deployment/traefik -- traefik version
# Dashboard mostra rotas ativas em http://localhost:9000/dashboard/
```

### Diagnóstico de TLS Challenge (Cert-Manager)

```bash
kubectl get challenges -A
kubectl describe challenge <name> -n apps
# Ver logs do Traefik durante HTTP-01
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep acme-challenge
```

### Verificar métricas Prometheus

```bash
kubectl port-forward -n traefik deployment/traefik 8082:8082
curl http://localhost:8082/metrics | grep traefik
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Cert-Manager](cert-manager.md)** | **[Próximo: Observability →](observability.md)**
