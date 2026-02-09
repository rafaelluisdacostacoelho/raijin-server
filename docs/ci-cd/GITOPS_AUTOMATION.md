# GitOps / CI/CD Automation

> **Navegação**: [← Voltar ao Índice CI/CD](INDEX.md)

---

## Visão Geral

O módulo **gitops** do raijin-server automatiza completamente a configuração de pipelines CI/CD para seus repositórios. Ele detecta automaticamente o tipo de aplicação e gera toda a infraestrutura necessária.

## Fluxo Completo

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. raijin-server gitops                                        │
│    └─> Informa URL do repositório                              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Detecção Automática de Tipo                                 │
│    ├─> Python (FastAPI, Django, Flask)                         │
│    ├─> Node.js (Next.js, React, Express)                       │
│    ├─> Go (Gin, Echo, Chi)                                     │
│    ├─> Static (HTML/CSS/JS)                                    │
│    └─> Supabase Custom                                         │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Geração Automática                                          │
│    ├─> Dockerfile (se não existir)                             │
│    ├─> k8s/deployment.yaml                                     │
│    ├─> k8s/service.yaml                                        │
│    ├─> k8s/ingress.yaml (com TLS)                              │
│    ├─> k8s/hpa.yaml                                            │
│    ├─> .github/workflows/cicd.yml                              │
│    └─> k8s/argocd-application.yaml                             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Commit e Push Automático                                    │
│    └─> git commit + git push                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Deploy ArgoCD Application                                   │
│    └─> kubectl apply -f argocd-application.yaml                │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Pipeline Ativa! 🚀                                           │
│    GitHub Actions → Harbor → ArgoCD → Kubernetes               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Uso

### Comando Básico

```bash
raijin-server gitops
```

### Inputs Interativos

```
URL do repositório GitHub: https://github.com/skelvynks/supabase
Nome da aplicação [supabase]: supabase
Namespace Kubernetes [supabase]: supabase
Domínio (ex: app.cryptidnest.com): supabase.cryptidnest.com
Harbor Registry URL [harbor.cryptidnest.com]: 
Harbor Project [library]: 
Número de replicas [2]: 2
```

---

## Detecção Automática

### Tipos Suportados

| Tipo | Detecção | Porta Padrão | Dockerfile |
|------|----------|--------------|------------|
| **Python API** | `requirements.txt` ou `pyproject.toml` | 8000 | FastAPI/Uvicorn |
| **Next.js** | `package.json` com `"next"` | 3000 | Multi-stage build |
| **React SPA** | `package.json` com `"react"` ou `"vite"` | 80 | Build + Nginx |
| **Node.js API** | `package.json` com `"express"` ou `"fastify"` | 3000 | Node.js |
| **Go** | `go.mod` | 8080 | Go build |
| **Static** | `index.html` | 80 | Nginx |
| **Supabase Custom** | `supabase/` directory | 8000 | Custom stack |

---

## Arquivos Gerados

### Estrutura do Repositório

```
your-repo/
├── k8s/
│   ├── namespace.yaml              # Namespace Kubernetes
│   ├── deployment.yaml             # Deployment com replicas, resources, probes
│   ├── service.yaml                # ClusterIP Service
│   ├── ingress.yaml                # Traefik Ingress com cert-manager TLS
│   ├── hpa.yaml                    # HorizontalPodAutoscaler
│   └── argocd-application.yaml     # ArgoCD Application (GitOps)
├── .github/
│   └── workflows/
│       └── cicd.yml                # GitHub Actions pipeline
├── Dockerfile                      # Gerado se não existir
└── GITOPS_README.md                # Documentação completa
```

### 1. Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: supabase
  namespace: supabase
spec:
  replicas: 2
  selector:
    matchLabels:
      app: supabase
  template:
    metadata:
      labels:
        app: supabase
    spec:
      containers:
      - name: supabase
        image: harbor.cryptidnest.com/library/supabase:latest
        ports:
        - containerPort: 8000
          name: http
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
```

### 2. Ingress com TLS

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
            name: supabase
            port:
              number: 80
```

### 3. GitHub Actions Pipeline

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  HARBOR_URL: harbor.cryptidnest.com
  IMAGE_NAME: library/supabase
  K8S_NAMESPACE: supabase

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    
    - name: Login to Harbor
      uses: docker/login-action@v3
      with:
        registry: ${{ env.HARBOR_URL }}
        username: ${{ secrets.HARBOR_USERNAME }}
        password: ${{ secrets.HARBOR_PASSWORD }}
    
    - name: Build and push
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ${{ env.HARBOR_URL }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

### 4. ArgoCD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: supabase
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/skelvynks/supabase
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: supabase
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

---

## Configuração

### 1. Secrets no GitHub

Configure no repositório: **Settings → Secrets and variables → Actions**

```bash
# Required secrets
HARBOR_USERNAME=<seu-usuario-harbor>
HARBOR_PASSWORD=<sua-senha-harbor>
```

### 2. Harbor Project

Crie o project no Harbor (se não existir):

```bash
# Via UI: harbor.cryptidnest.com → Projects → New Project
# Ou via API/CLI
```

### 3. DNS no Cloudflare

```
Type: A
Name: supabase
IPv4: <IP-DO-SERVIDOR>
Proxy: OFF
```

---

## Pipeline CI/CD

### Fluxo Completo

```
1. Developer Push
   └─> git push origin main

2. GitHub Actions Trigger
   ├─> Checkout code
   ├─> Build Docker image
   ├─> Tag: library/supabase:sha-abc123
   └─> Push to Harbor

3. ArgoCD Detect Change
   ├─> Poll repository every 3 minutes
   ├─> Compare manifests
   └─> Detect new image tag

4. ArgoCD Sync
   ├─> Apply k8s manifests
   ├─> Rolling update deployment
   └─> Wait for readiness probes

5. Application Live! 🚀
   └─> https://supabase.cryptidnest.com
```

### Estratégias de Deploy

#### Opção 1: Auto-Sync (Recomendado)

```yaml
syncPolicy:
  automated:
    prune: true      # Remove recursos deletados
    selfHeal: true   # Reverte mudanças manuais
```

**Vantagens**:
- ✅ Deploy automático ao push
- ✅ GitOps completo
- ✅ Sem intervenção manual

#### Opção 2: Manual Sync

```yaml
syncPolicy: {}  # Sem automated
```

**Usar quando**:
- Precisa de aprovação manual
- Deploy em horários específicos
- Ambiente de produção crítico

```bash
# Sync manual
argocd app sync supabase

# Ou pela UI
https://argocd.cryptidnest.com/applications/supabase
```

---

## Monitoramento

### Status ArgoCD

```bash
# Ver status da aplicação
kubectl get application supabase -n argocd

# Logs de sync
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller -f
```

### Status Kubernetes

```bash
# Ver pods
kubectl get pods -n supabase

# Ver deployment
kubectl describe deployment supabase -n supabase

# Ver logs
kubectl logs -n supabase -l app=supabase -f

# Ver ingress
kubectl get ingress -n supabase
```

### Verificar TLS

```bash
# Certificado
kubectl get certificate supabase-tls -n supabase

# Testar HTTPS
curl -I https://supabase.cryptidnest.com
```

---

## Troubleshooting

### Image pull failed

```bash
# Verificar secret do Harbor
kubectl get secret -n supabase

# Criar secret para pull de imagens privadas
kubectl create secret docker-registry harbor-creds \
  --docker-server=harbor.cryptidnest.com \
  --docker-username=<user> \
  --docker-password=<pass> \
  -n supabase

# Adicionar ao deployment
spec:
  template:
    spec:
      imagePullSecrets:
      - name: harbor-creds
```

### ArgoCD não sincroniza

```bash
# Forçar refresh
argocd app get supabase --refresh

# Ver erros
argocd app get supabase

# Logs do controller
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

### GitHub Actions falha

```bash
# Verificar secrets
# Settings → Secrets → Actions

# Testar login Harbor manualmente
docker login harbor.cryptidnest.com -u <user>

# Ver logs do workflow
# Actions → Select workflow run → View logs
```

---

## Casos de Uso

### 1. App Lovable + Supabase

```bash
raijin-server gitops

# Inputs
Repositório: https://github.com/skelvynks/lovable-app
Nome: lovable-app
Namespace: apps
Domínio: app.cryptidnest.com
Harbor Project: apps
Replicas: 3
```

**Resultado**: App rodando em https://app.cryptidnest.com com auto-deploy

### 2. API Python + FastAPI

```bash
raijin-server gitops

# Inputs
Repositório: https://github.com/user/api-python
Nome: api
Namespace: backend
Domínio: api.cryptidnest.com
```

**Detecção**: `requirements.txt` → Python API → FastAPI/Uvicorn

### 3. Frontend React

```bash
raijin-server gitops

# Inputs
Repositório: https://github.com/user/react-app
Nome: frontend
Domínio: frontend.cryptidnest.com
```

**Detecção**: `package.json` com React → SPA → Nginx

---

## Exemplo Completo

### Passo a Passo

```bash
# 1. Executar setup
raijin-server gitops

# 2. Configurar secrets no GitHub
# Settings → Secrets → Actions
HARBOR_USERNAME=admin
HARBOR_PASSWORD=<senha>

# 3. Push para main triggera pipeline
git push origin main

# 4. Acompanhar build
# Actions → Select workflow

# 5. Verificar deploy ArgoCD
kubectl get application supabase -n argocd -w

# 6. Testar aplicação
curl https://supabase.cryptidnest.com/health
```

---

## Remover Aplicação

```bash
# Via CLI
raijin-server uninstall gitops
# Informar nome: supabase

# Ou manual
kubectl delete application supabase -n argocd
kubectl delete namespace supabase
```

---

## Recursos Adicionais

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [GitHub Actions](https://docs.github.com/en/actions)
- [Harbor Registry](https://goharbor.io/docs/)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

---

## Próximos Passos

1. ✅ Configurar repositório com `raijin-server gitops`
2. ✅ Adicionar secrets no GitHub
3. ✅ Push para main
4. ✅ Verificar deploy automático
5. 🔄 Monitorar aplicação

**Dúvidas?** Veja documentação completa em `docs/ci-cd/INDEX.md`
