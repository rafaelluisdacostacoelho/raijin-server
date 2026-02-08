# Configuração de Domínios e Exposição de Serviços

Este guia explica como configurar DNS no Cloudflare e expor serviços Kubernetes com Traefik + cert-manager usando o domínio **cryptidnest.com** como exemplo.

---

## Índice

- [Arquitetura](#arquitetura)
- [Cloudflare DNS Setup](#cloudflare-dns-setup)
- [Traefik Ingress](#traefik-ingress)
- [cert-manager TLS](#cert-manager-tls)
- [Expor Novos Serviços](#expor-novos-serviços)
- [Troubleshooting](#troubleshooting)

---

## Arquitetura

```
Internet
   ↓
Cloudflare DNS (cryptidnest.com)
   ↓
Seu Servidor (IP público)
   ↓
Kubernetes Cluster
   ↓
Traefik Ingress Controller
   ↓
Services (Supabase, Harbor, etc)
```

### Fluxo de TLS

```
1. cert-manager solicita certificado ao Let's Encrypt
2. Let's Encrypt valida via HTTP-01 ou DNS-01 challenge
3. Certificado é armazenado como Kubernetes Secret
4. Traefik usa o Secret para servir HTTPS
```

---

## Cloudflare DNS Setup

### 1. Adicionar Registros DNS

Acesse o Cloudflare Dashboard → `cryptidnest.com` → DNS → Records

#### Opção A: Registro A (IP Direto)

```
Type: A
Name: supabase
IPv4: <IP-DO-SEU-SERVIDOR>
Proxy: OFF (Desabilitado - cinza)
TTL: Auto
```

**Resultado**: `supabase.cryptidnest.com → IP-DO-SERVIDOR`

#### Opção B: Registro CNAME (Alias)

Se já tiver um wildcard ou registro principal:

```
Type: CNAME
Name: supabase
Target: cluster.cryptidnest.com
Proxy: OFF
TTL: Auto
```

### 2. Configuração Recomendada

**⚠️ IMPORTANTE**: Desabilite o proxy do Cloudflare (ícone cinza) para:
- ✅ Permitir que cert-manager valide via HTTP-01
- ✅ Traefik gerenciar TLS diretamente
- ✅ WebSockets funcionarem corretamente (Supabase Realtime)

**Quando usar Proxy ON** (ícone laranja):
- Se precisar de proteção DDoS do Cloudflare
- Nesse caso, use DNS-01 challenge no cert-manager com API Token

### 3. Verificar Propagação DNS

```bash
# Verificar registro A
dig +short supabase.cryptidnest.com

# Verificar com DNS do Cloudflare
dig @1.1.1.1 supabase.cryptidnest.com

# Verificar propagação global
nslookup supabase.cryptidnest.com
```

**Tempo de propagação**: 2-5 minutos

---

## Traefik Ingress

### 1. Criar Ingress Resource

Template genérico para qualquer serviço:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <service-name>-ingress
  namespace: <namespace>
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - <service>.cryptidnest.com
    secretName: <service>-tls
  rules:
  - host: <service>.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: <service-name>
            port:
              number: <port>
```

### 2. Exemplo: Supabase

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: supabase-ingress
  namespace: supabase
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - supabase.cryptidnest.com
    secretName: supabase-tls
  rules:
  - host: supabase.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: supabase-kong
            port:
              number: 8000
```

### 3. Aplicar Ingress

```bash
kubectl apply -f ingress.yaml

# Verificar
kubectl get ingress -n supabase
kubectl describe ingress supabase-ingress -n supabase
```

---

## cert-manager TLS

### 1. ClusterIssuer (Let's Encrypt)

#### HTTP-01 Challenge (Recomendado para IP direto)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@cryptidnest.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: traefik
```

#### DNS-01 Challenge (Para Cloudflare Proxy ON)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod-dns
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@cryptidnest.com
    privateKeySecretRef:
      name: letsencrypt-prod-dns
    solvers:
    - dns01:
        cloudflare:
          email: seu-email@exemplo.com
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```

**Criar Secret do Cloudflare API Token**:

```bash
# 1. Gerar API Token no Cloudflare:
#    Dashboard → My Profile → API Tokens → Create Token
#    Template: Edit zone DNS
#    Permissions: Zone:DNS:Edit
#    Zone Resources: Include → Specific zone → cryptidnest.com

# 2. Criar Secret no Kubernetes
kubectl create secret generic cloudflare-api-token \
  --from-literal=api-token=<SEU-API-TOKEN> \
  -n cert-manager
```

### 2. Verificar Certificado

```bash
# Ver certificates
kubectl get certificates -A

# Ver status detalhado
kubectl describe certificate supabase-tls -n supabase

# Ver logs do cert-manager
kubectl logs -n cert-manager deploy/cert-manager -f

# Verificar secret TLS criado
kubectl get secret supabase-tls -n supabase
```

### 3. Renovação Automática

cert-manager renova certificados automaticamente **30 dias antes da expiração**.

```bash
# Forçar renovação manual (se necessário)
kubectl delete certificate supabase-tls -n supabase
kubectl apply -f ingress.yaml
```

---

## Expor Novos Serviços

### Template - Checklist Completo

Para expor qualquer novo serviço (exemplo: `grafana.cryptidnest.com`):

#### 1. **Cloudflare DNS**

```
Type: A
Name: grafana
IPv4: <IP-DO-SERVIDOR>
Proxy: OFF
```

#### 2. **Kubernetes Service** (ClusterIP)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: monitoring
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 3000
  selector:
    app: grafana
```

#### 3. **Ingress Resource**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grafana-ingress
  namespace: monitoring
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - grafana.cryptidnest.com
    secretName: grafana-tls
  rules:
  - host: grafana.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: grafana
            port:
              number: 80
```

#### 4. **Aplicar e Verificar**

```bash
# Aplicar manifests
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Aguardar certificado (1-2 minutos)
kubectl get certificate grafana-tls -n monitoring -w

# Testar acesso
curl -I https://grafana.cryptidnest.com
```

### Exemplo: Harbor (Container Registry)

```yaml
# DNS: harbor.cryptidnest.com → A → IP-SERVIDOR

# Ingress
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: harbor-ingress
  namespace: harbor
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
    # Harbor precisa de uploads grandes
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - harbor.cryptidnest.com
    secretName: harbor-tls
  rules:
  - host: harbor.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: harbor-portal
            port:
              number: 80
```

### Exemplo: Argo CD

```yaml
# DNS: argocd.cryptidnest.com → A → IP-SERVIDOR

# Ingress
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
    # Argo CD usa gRPC
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - argocd.cryptidnest.com
    secretName: argocd-tls
  rules:
  - host: argocd.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
```

---

## Padrão de Nomenclatura

Mantenha consistência nos subdomínios:

```
supabase.cryptidnest.com    # Backend as a Service
harbor.cryptidnest.com      # Container Registry
argocd.cryptidnest.com      # GitOps CD
grafana.cryptidnest.com     # Monitoring
prometheus.cryptidnest.com  # Metrics
minio.cryptidnest.com       # Object Storage
vault.cryptidnest.com       # Secrets Management

# Apps Lovable
app1.cryptidnest.com
app2.cryptidnest.com
```

---

## CI/CD - Automatizar Deploy de Ingress

### GitHub Actions - Deploy Automático

```yaml
# .github/workflows/deploy-ingress.yml
name: Deploy Ingress

on:
  push:
    branches: [main]
    paths:
      - 'k8s/ingress/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup kubectl
      uses: azure/setup-kubectl@v3
    
    - name: Configure kubeconfig
      run: |
        mkdir -p ~/.kube
        echo "${{ secrets.KUBECONFIG }}" | base64 -d > ~/.kube/config
    
    - name: Deploy Ingress
      run: |
        kubectl apply -f k8s/ingress/
        
    - name: Wait for Certificate
      run: |
        kubectl wait --for=condition=ready certificate \
          --all --timeout=300s -n production
    
    - name: Verify HTTPS
      run: |
        curl -I https://${{ vars.SERVICE_DOMAIN }}
```

### ArgoCD - GitOps

```yaml
# argocd/ingress-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ingress-configs
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/k8s-config
    targetRevision: main
    path: ingress/
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

## Troubleshooting

### Certificate não é criado

```bash
# 1. Verificar ClusterIssuer
kubectl get clusterissuer
kubectl describe clusterissuer letsencrypt-prod

# 2. Ver challenges (validação HTTP/DNS)
kubectl get challenges -A
kubectl describe challenge <challenge-name> -n <namespace>

# 3. Ver logs cert-manager
kubectl logs -n cert-manager deploy/cert-manager -f

# 4. Verificar se HTTP-01 challenge é acessível
curl http://supabase.cryptidnest.com/.well-known/acme-challenge/
```

**Problemas comuns**:
- ❌ Cloudflare Proxy ON (laranja) → Mude para OFF ou use DNS-01
- ❌ Firewall bloqueando porta 80 → Abra HTTP para validação
- ❌ DNS não propagado → Aguarde 5 minutos

### Traefik não roteia tráfego

```bash
# 1. Verificar Ingress
kubectl get ingress -A
kubectl describe ingress <name> -n <namespace>

# 2. Ver logs Traefik
kubectl logs -n kube-system deploy/traefik -f

# 3. Verificar Service existe
kubectl get svc <service-name> -n <namespace>

# 4. Testar acesso interno
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://<service-name>.<namespace>.svc:<port>
```

### HTTPS não funciona

```bash
# 1. Verificar certificado
kubectl get certificate -n <namespace>
kubectl describe certificate <name> -n <namespace>

# 2. Ver secret TLS
kubectl get secret <tls-secret-name> -n <namespace>
kubectl describe secret <tls-secret-name> -n <namespace>

# 3. Testar TLS
openssl s_client -connect supabase.cryptidnest.com:443 -servername supabase.cryptidnest.com

# 4. Verificar annotations do Ingress
kubectl get ingress <name> -n <namespace> -o yaml | grep annotations -A 5
```

### DNS não resolve

```bash
# 1. Verificar registro no Cloudflare
dig supabase.cryptidnest.com
dig @1.1.1.1 supabase.cryptidnest.com

# 2. Testar com different DNS servers
dig @8.8.8.8 supabase.cryptidnest.com
dig @1.0.0.1 supabase.cryptidnest.com

# 3. Verificar propagação global
https://dnschecker.org/#A/supabase.cryptidnest.com

# 4. Limpar cache local
sudo systemd-resolve --flush-caches  # Linux
dscacheutil -flushcache              # macOS
```

---

## Referências

- [Traefik Ingress Controller](https://doc.traefik.io/traefik/providers/kubernetes-ingress/)
- [cert-manager](https://cert-manager.io/docs/)
- [Let's Encrypt](https://letsencrypt.org/docs/)
- [Cloudflare DNS](https://developers.cloudflare.com/dns/)
- [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/)

---

## Próximos Passos

1. ✅ Configurar DNS no Cloudflare
2. ✅ Aplicar Ingress com Traefik
3. ✅ Verificar certificado TLS
4. ✅ Testar acesso HTTPS
5. 🔄 Replicar para outros serviços
6. 🔄 Automatizar com CI/CD

**Dúvidas?** Consulte a documentação completa em `docs/tools/supabase.md`
