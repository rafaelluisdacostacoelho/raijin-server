# Copilot Prompt: Publicar Novo App no Kubernetes

## Contexto

Você é um agente especializado em publicar aplicativos em Kubernetes com CI/CD automatizado.

A **infraestrutura raijin-server JÁ ESTÁ CONFIGURADA E RODANDO** no servidor de produção, incluindo:
- Kubernetes (K3s) rodando ✅
- Argo CD para GitOps ✅
- Harbor registry privado ✅
- Vault para secrets ✅
- Traefik ingress com SSL ✅
- Prometheus + Grafana monitorando ✅

**Objetivo**: Publicar um **NOVO APLICATIVO** (website, API, SPA, etc.) nessa infraestrutura existente.

### Stack Tecnológica Instalada

- **Kubernetes**: K3s com controle total
- **GitOps**: Argo CD + Argo Workflows
- **Registry**: Harbor (com scan de vulnerabilidades)
- **Secrets**: HashiCorp Vault + External Secrets Operator
- **Ingress**: Traefik
- **Observability**: Prometheus + Grafana + Loki
- **Security**: Cert-Manager + Calico Network Policies

### Estrutura Base Raijin-Server

```
raijin-server/
├── examples/
│   ├── monorepo-app/          # Exemplo de referência
│   ├── ci-cd/                 # Templates de pipelines
│   └── secrets/               # Templates de secrets
├── src/raijin_server/
│   └── modules/               # Módulos de instalação
└── docs/
    ├── tools/                 # Documentação das ferramentas
    └── INFRASTRUCTURE_GUIDE.md
```

---

## Objetivo da Tarefa

Publicar um novo aplicativo no servidor Kubernetes produtivo, incluindo:

1. **Estrutura do Projeto**: Frontend, Backend (se aplicável), Kubernetes manifests
2. **Pipeline CI**: Build automático com GitHub Actions ou Argo Workflows
3. **GitOps CD**: Deploy automático via Argo CD (TST auto, PRD manual)
4. **Secrets Management**: Secrets gerenciados pelo Vault
5. **Exposição Pública**: App acessível na internet via domínio (Traefik + SSL)
6. **Monitoring**: Métricas no Prometheus/Grafana

---

## Instruções Detalhadas

### 1. Análise do Projeto Atual

Antes de começar, você deve:

**a) Identificar a estrutura do projeto:**
```bash
# Procure por arquivos de configuração
- package.json, tsconfig.json (Frontend Node/React/Next)
- go.mod, main.go (Backend Go)
- requirements.txt, pyproject.toml (Backend Python)
- Dockerfile(s) existentes
- docker-compose.yml
```

**b) Determinar tecnologias:**
- Linguagem do frontend (React, Vue, Angular, Next.js, etc.)
- Linguagem do backend (Go, Python, Node.js, Java, etc.)
- Banco de dados (PostgreSQL, MySQL, MongoDB, Redis)
- Integrações externas (Email, S3, APIs)

**c) Verificar requisitos especiais:**
- Variáveis de ambiente necessárias
- Secrets sensíveis (API keys, tokens, senhas)
- Portas e serviços
- Dependências de build (npm, go, pip, maven)

### 2. Criar Estrutura do Monorepo

Use como base o exemplo em `examples/monorepo-app/`:

```
my-app/
├── .github/
│   └── workflows/
│       ├── ci-tst.yml          # Pipeline TST (auto-deploy)
│       └── ci-prd.yml          # Pipeline PRD (manual)
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── Dockerfile.dev          # Dev com hot-reload
│   ├── nginx.conf              # Produção
│   └── package.json
├── backend/
│   ├── cmd/
│   ├── internal/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── go.mod (ou requirements.txt)
├── kubernetes/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── frontend/
│   │   │   ├── deployment.yaml
│   │   │   └── service.yaml
│   │   ├── backend/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── configmap.yaml
│   │   ├── database/
│   │   │   ├── statefulset.yaml
│   │   │   ├── service.yaml
│   │   │   └── pvc.yaml
│   │   ├── externalsecrets.yaml
│   │   └── ingress.yaml
│   └── overlays/
│       ├── tst/
│       │   ├── kustomization.yaml
│       │   └── patches/
│       └── prd/
│           ├── kustomization.yaml
│           └── patches/
├── scripts/
│   ├── dev.sh                  # Docker-compose dev
│   ├── build-all.sh            # Build local
│   └── vault-setup.sh          # Configurar secrets no Vault
├── docker-compose.yml          # Desenvolvimento local
├── Makefile                    # Comandos utilitários
└── README.md                   # Documentação do projeto
```

### 3. Dockerfiles (Multi-stage builds)

**Frontend (React/Vue/Next.js):**
```dockerfile
# Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Backend (Go):**
```dockerfile
# Dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o server ./cmd/server

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/server .
EXPOSE 8080
CMD ["./server"]
```

### 4. Kubernetes Base Manifests

**namespace.yaml:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: myapp-tst
  labels:
    environment: tst
    monitoring: "true"
---
apiVersion: v1
kind: Namespace
metadata:
  name: myapp-prd
  labels:
    environment: prd
    monitoring: "true"
```

**frontend/deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  labels:
    app: frontend
    component: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
        component: web
    spec:
      containers:
        - name: frontend
          image: harbor.local/tst/myapp-frontend:latest  # Substituir via Kustomize
          ports:
            - containerPort: 80
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "256Mi"
              cpu: "200m"
```

**backend/deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  labels:
    app: backend
    component: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
        component: api
    spec:
      containers:
        - name: backend
          image: harbor.local/tst/myapp-backend:latest  # Substituir via Kustomize
          ports:
            - containerPort: 8080
              protocol: TCP
          env:
            - name: PORT
              value: "8080"
            - name: DB_HOST
              value: postgres
            - name: DB_PORT
              value: "5432"
            - name: DB_NAME
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_name
            - name: DB_USER
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_user
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_password
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
```

**externalsecrets.yaml:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: myapp-secrets
    creationPolicy: Owner
  dataFrom:
    - extract:
        key: secret/myapp/database
    - extract:
        key: secret/myapp/api-keys
```

**ingress.yaml:**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
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
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 8080
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 80
```

### 5. Kustomize Overlays

**overlays/tst/kustomization.yaml:**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: myapp-tst

bases:
  - ../../base

images:
  - name: harbor.local/tst/myapp-frontend
    newTag: dev-latest
  - name: harbor.local/tst/myapp-backend
    newTag: dev-latest

replicas:
  - name: frontend
    count: 1
  - name: backend
    count: 1

patches:
  - path: ingress-patch.yaml
```

**overlays/prd/kustomization.yaml:**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: myapp-prd

bases:
  - ../../base

images:
  - name: harbor.local/prd/myapp-frontend
    newTag: v1.0.0
  - name: harbor.local/prd/myapp-backend
    newTag: v1.0.0

replicas:
  - name: frontend
    count: 3
  - name: backend
    count: 3

patches:
  - path: resources-patch.yaml
  - path: hpa-patch.yaml
```

### 6. Pipeline CI (GitHub Actions)

**Base em:** `examples/ci-cd/github-actions-tst.yml`

**Adaptações necessárias:**
- Detectar mudanças em `frontend/` ou `backend/` (path filters)
- Usar Harbor registry IP:porta corretos
- Configurar Trivy scan (warning em TST, bloqueante em PRD)
- Configurar Semgrep SAST
- Update Kustomize image tag após push

**.github/workflows/ci-tst.yml:**
```yaml
name: CI/CD - TST

on:
  push:
    branches: [develop]
    paths:
      - 'frontend/**'
      - 'backend/**'
      - 'kubernetes/**'

env:
  HARBOR_REGISTRY: 192.168.1.100:30880  # Ajustar IP
  HARBOR_PROJECT: tst
  
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      frontend: ${{ steps.filter.outputs.frontend }}
      backend: ${{ steps.filter.outputs.backend }}
    steps:
      - uses: actions/checkout@v3
      - uses: dorny/paths-filter@v2
        id: filter
        with:
          filters: |
            frontend:
              - 'frontend/**'
            backend:
              - 'backend/**'

  build-frontend:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      # Semgrep, build, Trivy, push...
      
  build-backend:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      # Semgrep, build, Trivy, push...
```

### 7. Argo CD Applications

**kubernetes/argocd-apps.yaml:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-tst
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/myapp.git
    targetRevision: develop
    path: kubernetes/overlays/tst
  destination:
    server: https://kubernetes.default.svc
    namespace: myapp-tst
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-prd
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/myapp.git
    targetRevision: main
    path: kubernetes/overlays/prd
  destination:
    server: https://kubernetes.default.svc
    namespace: myapp-prd
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
    # PRD: Manual sync apenas
```

### 8. Configurar Secrets no Vault

**scripts/vault-setup.sh:**
```bash
#!/bin/bash
set -e

VAULT_POD="vault-0"
VAULT_NS="vault"

echo "Configurando secrets no Vault..."

# Database credentials
kubectl -n $VAULT_NS exec $VAULT_POD -- vault kv put secret/myapp/database \
  db_name=myapp \
  db_user=myapp_user \
  db_password=$(openssl rand -base64 32)

# API Keys
kubectl -n $VAULT_NS exec $VAULT_POD -- vault kv put secret/myapp/api-keys \
  jwt_secret=$(openssl rand -base64 64) \
  api_key=$(uuidgen)

echo "✅ Secrets configurados com sucesso!"
echo "Use ExternalSecret para sincronizar no namespace da aplicação"
```

### 9. Docker Compose para Dev

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - VITE_API_URL=http://localhost:8080

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    ports:
      - "8080:8080"
    volumes:
      - ./backend:/app
    environment:
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=myapp
      - DB_USER=dev
      - DB_PASSWORD=dev123
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev123
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

### 10. Makefile

```makefile
.PHONY: help dev build-all test-all deploy-tst deploy-prd

help:
	@echo "Comandos disponíveis:"
	@echo "  make dev          - Inicia ambiente de desenvolvimento"
	@echo "  make build-all    - Build de todas as imagens"
	@echo "  make test-all     - Executa todos os testes"
	@echo "  make deploy-tst   - Deploy manual em TST"
	@echo "  make deploy-prd   - Deploy manual em PRD"

dev:
	docker-compose up -d
	@echo "Frontend: http://localhost:3000"
	@echo "Backend:  http://localhost:8080"

build-all:
	docker build -t myapp-frontend:local ./frontend
	docker build -t myapp-backend:local ./backend

test-all:
	cd frontend && npm test
	cd backend && go test ./...

deploy-tst:
	kubectl apply -k kubernetes/overlays/tst

deploy-prd:
	kubectl apply -k kubernetes/overlays/prd
```

---

## Checklist de Validação

Após configurar tudo, valide:

- [ ] **Estrutura**: Monorepo organizado com frontend/, backend/, kubernetes/
- [ ] **Docker**: Dockerfiles multi-stage otimizados
- [ ] **K8s Base**: Deployments, Services, Ingress, ExternalSecrets
- [ ] **Kustomize**: Overlays TST e PRD funcionando
- [ ] **Pipeline CI**: GitHub Actions ou Argo Workflows configurado
- [ ] **Argo CD**: Applications criadas para TST (auto-sync) e PRD (manual)
- [ ] **Secrets**: Vault configurado e ExternalSecrets sincronizando
- [ ] **Harbor**: Imagens sendo pushed corretamente
- [ ] **Dev Local**: docker-compose funciona
- [ ] **Makefile**: Comandos básicos implementados
- [ ] **README.md**: Documentação completa do projeto

---

## Comandos de Teste

```bash
# 1. Testar build local
docker-compose up --build

# 2. Testar Kustomize
kubectl kustomize kubernetes/overlays/tst
kubectl kustomize kubernetes/overlays/prd

# 3. Deploy manual TST
kubectl apply -k kubernetes/overlays/tst

# 4. Verificar pods
kubectl get pods -n myapp-tst

# 5. Verificar Argo CD sync
kubectl get applications -n argocd

# 6. Testar ingress
curl -H "Host: myapp-tst.local" http://192.168.1.100
```

---

## Referências

- Exemplo completo: `examples/monorepo-app/`
- Pipelines CI/CD: `examples/ci-cd/`
- Secrets: `examples/secrets/`
- Documentação ferramentas: `docs/tools/`
- Guia infraestrutura: `docs/INFRASTRUCTURE_GUIDE.md`

---

## Output Esperado

Ao final, você deve entregar:

1. **Estrutura completa do monorepo** conforme especificado
2. **Arquivos de configuração** (Dockerfiles, Kustomize, Pipeline)
3. **README.md** do projeto com instruções
4. **Scripts auxiliares** (Makefile, vault-setup.sh, etc.)
5. **Documentação de secrets** necessários
6. **Instruções de deploy** para TST e PRD

**Qualidade esperada:**
- Código limpo e bem comentado
- Seguir padrões Kubernetes
- Security best practices (secrets, network policies)
- Resource limits definidos
- Health checks configurados
- Observabilidade (labels, prometheus metrics)
