# Publicação de Aplicações Web

Guia completo para publicar sites, APIs e sistemas na internet usando Traefik + Cert-Manager.

## Índice

- [Arquitetura](#arquitetura)
- [Configuração Única (Roteador)](#configuração-única-roteador)
- [Publicar Nova Aplicação](#publicar-nova-aplicação)
- [Exemplos Práticos](#exemplos-práticos)
- [Certificados TLS](#certificados-tls)
- [Troubleshooting](#troubleshooting)

---

## Arquitetura

```
                               INTERNET
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │       IP Público Fixo       │
                    │        203.0.113.50         │
                    │                             │
                    │      Porta 80  (HTTP)       │
                    │      Porta 443 (HTTPS)      │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────┴───────────────┐ 
                    │        ROTEADOR             │
                    │                             │
                    │  Port Forward (1x):         │
                    │  80  → 192.168.1.100:30080  │
                    │  443 → 192.168.1.100:30443  │
                    └─────────────┬───────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│                              TRAEFIK                                  │
│                       (Ingress Controller)                            │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                     HOST-BASED ROUTING                          │  │
│  │                                                                 │  │
│  │  O Traefik lê o HOSTNAME (Header "Host" / SNI) de cada          │  │
│  │  requisição e roteia para o serviço correto:                    │  │
│  │                                                                 │  │
│  │    hisentient.com        →  landing-svc:80                      │  │
│  │    api.hisentient.com    →  api-svc:8080                        │  │
│  │    app.hisentient.com    →  webapp-svc:3000                     │  │
│  │    grafana.hisentient.com→  grafana-svc:3000                    │  │
│  │    cliente.com.br        →  cliente-app-svc:80                  │  │
│  │                                                                 │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    TLS TERMINATION                              │  │
│  │                                                                 │  │
│  │  • Traefik recebe conexão HTTPS                                 │  │
│  │  • Descriptografa usando certificado do domínio                 │  │
│  │  • Encaminha HTTP para o serviço interno                        │  │
│  │  • Certificados gerenciados pelo cert-manager (Let's Encrypt)   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
      ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
      │   Namespace   │   │   Namespace   │   │   Namespace   │
      │   landing     │   │   api         │   │   cliente     │
      │               │   │               │   │               │
      │ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
      │ │  Pod(s)   │ │   │ │  Pod(s)   │ │   │ │  Pod(s)   │ │
      │ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
      └───────────────┘   └───────────────┘   └───────────────┘
```

---

## Configuração Única (Roteador)

Esta configuração é feita **APENAS UMA VEZ**. Depois, você nunca mais precisa mexer no roteador.

### Port Forward

No painel admin do roteador (geralmente http://192.168.1.1):

| Nome | Porta Externa | IP Interno | Porta Interna | Protocolo |
|------|---------------|------------|---------------|-----------|
| `HTTP` | **80** | 192.168.1.100 | **30080** | TCP |
| `HTTPS` | **443** | 192.168.1.100 | **30443** | TCP |

### Verificar se funciona

```bash
# De fora da rede (ou use celular com 4G)
curl -I http://203.0.113.50

# Deve retornar algo como:
# HTTP/1.1 404 Not Found  (Traefik respondendo, mas sem rota configurada)
```

---

## Publicar Nova Aplicação

Para cada nova aplicação, você precisa de **3 passos**:

### Passo 1: DNS (Cloudflare)

Adicione um registro A apontando para seu IP público:

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A | `@` ou `subdomain` | `203.0.113.50` | DNS only (cinza) | Auto |

**Exemplos:**

```
# Domínio raiz
hisentient.com         A    203.0.113.50

# Subdomínio
api.hisentient.com     A    203.0.113.50
app.hisentient.com     A    203.0.113.50

# Wildcard (todos os subdomínios)
*.hisentient.com       A    203.0.113.50
```

> ⚠️ **IMPORTANTE**: Mantenha o proxy do Cloudflare **DESLIGADO** (ícone cinza) para o certificado Let's Encrypt funcionar via HTTP-01 challenge.

### Passo 2: Deploy da Aplicação

```yaml
# minha-app.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: minha-app
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minha-app
  namespace: minha-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: minha-app
  template:
    metadata:
      labels:
        app: minha-app
    spec:
      containers:
      - name: app
        image: minha-imagem:latest
        ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: minha-app-svc
  namespace: minha-app
spec:
  selector:
    app: minha-app
  ports:
  - port: 80
    targetPort: 8080
```

### Passo 3: IngressRoute + Certificado

```yaml
# minha-app-ingress.yaml
---
# Certificado TLS (Let's Encrypt automático)
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: minha-app-cert
  namespace: minha-app
spec:
  secretName: minha-app-tls
  issuerRef:
    name: letsencrypt-http
    kind: ClusterIssuer
  dnsNames:
    - app.hisentient.com
---
# Rota HTTPS
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: minha-app-https
  namespace: minha-app
spec:
  entryPoints:
    - websecure
  routes:
  - match: Host(`app.hisentient.com`)
    kind: Rule
    services:
    - name: minha-app-svc
      port: 80
  tls:
    secretName: minha-app-tls
---
# Redirect HTTP → HTTPS
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: minha-app-http
  namespace: minha-app
spec:
  entryPoints:
    - web
  routes:
  - match: Host(`app.hisentient.com`)
    kind: Rule
    middlewares:
    - name: redirect-https
    services:
    - name: minha-app-svc
      port: 80
---
# Middleware de redirecionamento
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: redirect-https
  namespace: minha-app
spec:
  redirectScheme:
    scheme: https
    permanent: true
```

### Aplicar

```bash
kubectl apply -f minha-app.yaml
kubectl apply -f minha-app-ingress.yaml

# Verificar certificado (aguarde ~1-2 minutos)
kubectl get certificate -n minha-app
```

---

## Exemplos Práticos

### Site Estático (nginx)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: website
  namespace: website
spec:
  replicas: 2
  selector:
    matchLabels:
      app: website
  template:
    metadata:
      labels:
        app: website
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        volumeMounts:
        - name: html
          mountPath: /usr/share/nginx/html
      volumes:
      - name: html
        configMap:
          name: website-html
```

### API Backend (Node.js/Python/Go)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: harbor.asgard.internal:30880/prd/minha-api:v1.0.0
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: database-url
```

### Múltiplos Domínios para Mesmo App

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: multi-domain
  namespace: minha-app
spec:
  entryPoints:
    - websecure
  routes:
  - match: Host(`hisentient.com`) || Host(`www.hisentient.com`) || Host(`hisentient.com.br`)
    kind: Rule
    services:
    - name: minha-app-svc
      port: 80
  tls:
    secretName: multi-domain-tls
```

### Path-Based Routing (vários apps no mesmo domínio)

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: path-routing
  namespace: default
spec:
  entryPoints:
    - websecure
  routes:
  # hisentient.com/api/* → api-svc
  - match: Host(`hisentient.com`) && PathPrefix(`/api`)
    kind: Rule
    middlewares:
    - name: strip-api-prefix
    services:
    - name: api-svc
      namespace: api
      port: 8080
  # hisentient.com/* → frontend-svc
  - match: Host(`hisentient.com`)
    kind: Rule
    services:
    - name: frontend-svc
      namespace: frontend
      port: 80
  tls:
    secretName: hisentient-tls
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-api-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /api
```

---

## Certificados TLS

### Como funciona

1. Você cria um `Certificate` resource
2. O cert-manager detecta e cria um `CertificateRequest`
3. O cert-manager cria um `Challenge` (HTTP-01 ou DNS-01)
4. Let's Encrypt acessa `http://seudominio.com/.well-known/acme-challenge/xxx`
5. Traefik responde com o token de validação
6. Let's Encrypt valida e emite o certificado
7. cert-manager salva no `Secret` especificado
8. Certificado renova automaticamente antes de expirar (90 dias)

### Verificar status

```bash
# Ver certificados
kubectl get certificate -A

# Ver detalhes
kubectl describe certificate meu-cert -n meu-namespace

# Ver challenges pendentes
kubectl get challenges -A

# Ver logs do cert-manager
kubectl logs -n cert-manager -l app=cert-manager -f
```

### Wildcard Certificate (avançado)

Para certificado wildcard (`*.hisentient.com`), você precisa usar **DNS-01 challenge** com Cloudflare:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-dns
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: seu@email.com
    privateKeySecretRef:
      name: letsencrypt-dns-key
    solvers:
    - dns01:
        cloudflare:
          email: seu@email.com
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
---
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-api-token
  namespace: cert-manager
type: Opaque
stringData:
  api-token: "seu-cloudflare-api-token"
```

---

## Troubleshooting

### Certificado não emite

```bash
# 1. Verificar DNS
dig +short meudominio.com

# 2. Verificar se porta 80 está aberta
curl -I http://meudominio.com/.well-known/acme-challenge/test

# 3. Ver challenges
kubectl get challenges -A
kubectl describe challenge <nome> -n <namespace>

# 4. Ver eventos
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### Erro 404 ao acessar

```bash
# Verificar IngressRoute
kubectl get ingressroute -A

# Verificar se o serviço existe
kubectl get svc -n <namespace>

# Verificar endpoints
kubectl get endpoints -n <namespace>

# Logs do Traefik
kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f
```

### Erro 502 Bad Gateway

```bash
# Pod está rodando?
kubectl get pods -n <namespace>

# Logs do pod
kubectl logs -n <namespace> <pod-name>

# Serviço aponta para pods corretos?
kubectl describe svc <service-name> -n <namespace>
```

---

## Checklist para Nova Aplicação

- [ ] DNS configurado no Cloudflare (proxy **desligado**)
- [ ] Namespace criado
- [ ] Deployment criado
- [ ] Service criado
- [ ] Certificate criado
- [ ] IngressRoute HTTPS criado
- [ ] IngressRoute HTTP (redirect) criado
- [ ] Certificado em estado `Ready: True`
- [ ] Teste de acesso via HTTPS

---

## Resumo de Portas

| Uso | Porta Pública | NodePort Traefik | Descrição |
|-----|---------------|------------------|-----------|
| HTTP | 80 | 30080 | Redirect para HTTPS |
| HTTPS | 443 | 30443 | Tráfego principal |

**Todas as aplicações usam as mesmas portas 80/443.** O roteamento é feito pelo hostname.
