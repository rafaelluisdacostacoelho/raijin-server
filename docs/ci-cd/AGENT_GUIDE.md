# Agent Guide: Monorepo CI/CD Configuration

> 🤖 **Para agentes autônomos**: Este guia contém instruções passo a passo para configurar um monorepo e integrá-lo com a infraestrutura raijin-server.

---

## Visão Geral

Este guia automatiza a configuração de um projeto monorepo para deploy com:
- **GitOps**: Argo CD (continuous delivery)
- **CI Pipeline**: Argo Workflows ou GitHub Actions
- **Registry**: Harbor (com scanning)
- **Secrets**: Vault + External Secrets Operator
- **Kubernetes**: K3s com Traefik ingress

---

## Pré-requisitos Verificáveis

Execute estas validações antes de iniciar:

```bash
# 1. Verificar cluster Kubernetes
kubectl cluster-info

# 2. Verificar Argo CD instalado
kubectl get pods -n argocd

# 3. Verificar Harbor
kubectl get pods -n harbor

# 4. Verificar Vault
kubectl get pods -n vault

# 5. Verificar External Secrets Operator
kubectl get pods -n external-secrets

# 6. Obter IP do Harbor
HARBOR_IP=$(kubectl get svc -n harbor harbor-portal -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
HARBOR_PORT=$(kubectl get svc -n harbor harbor-portal -o jsonpath='{.spec.ports[0].port}')
echo "Harbor: $HARBOR_IP:$HARBOR_PORT"
```

**Saídas esperadas:**
- Todos os namespaces devem existir
- Todos os pods devem estar Running
- Harbor deve ter um IP acessível

Se alguma validação falhar, instale o módulo correspondente com `raijin install <module>`.

---

## Fase 1: Análise do Projeto Existente

### Passo 1.1: Identificar Estrutura

```bash
# Listar arquivos do projeto
find . -maxdepth 3 -type f \( -name "*.json" -o -name "*.yaml" -o -name "*.toml" -o -name "*.mod" -o -name "Dockerfile" \) 2>/dev/null
```

**Procure por:**
- `package.json` → Frontend Node.js
- `go.mod` → Backend Go
- `requirements.txt` ou `pyproject.toml` → Backend Python
- `pom.xml` → Backend Java
- `Dockerfile` → Aplicação containerizada
- `docker-compose.yml` → Setup dev existente

### Passo 1.2: Determinar Tecnologias

**Frontend:**
```bash
# React/Next.js
grep -r "react" package.json 2>/dev/null

# Vue
grep -r "vue" package.json 2>/dev/null

# Angular
grep -r "@angular" package.json 2>/dev/null
```

**Backend:**
```bash
# Go
test -f go.mod && echo "Backend: Go"

# Python
test -f requirements.txt && echo "Backend: Python"

# Node.js
grep -q "express\|fastify\|koa" package.json 2>/dev/null && echo "Backend: Node.js"
```

### Passo 1.3: Mapear Dependências

```bash
# Banco de dados
grep -ri "postgres\|mysql\|mongodb" . --include="*.{json,yaml,yml,toml,env}" 2>/dev/null

# Cache
grep -ri "redis\|memcached" . --include="*.{json,yaml,yml,toml,env}" 2>/dev/null

# Message queue
grep -ri "rabbitmq\|kafka\|nats" . --include="*.{json,yaml,yml,toml,env}" 2>/dev/null
```

### Passo 1.4: Extrair Configurações

```bash
# Portas
grep -rh "PORT\|port" . --include="*.env*" 2>/dev/null | sort -u

# Variáveis de ambiente necessárias
grep -rh "process.env\|os.Getenv\|os.environ" . --include="*.{js,ts,go,py}" 2>/dev/null | \
  sed -n 's/.*[("]\([A-Z_][A-Z0-9_]*\)[")].*/\1/p' | sort -u
```

**Armazene estas informações** para usar nas próximas fases.

---

## Fase 2: Criar Estrutura do Monorepo

### Passo 2.1: Criar Diretórios Base

```bash
# Estrutura principal
mkdir -p .github/workflows
mkdir -p frontend/src
mkdir -p backend/{cmd,internal}
mkdir -p kubernetes/base/{frontend,backend,database,redis}
mkdir -p kubernetes/overlays/{tst,prd}
mkdir -p scripts
```

### Passo 2.2: Mover Arquivos Existentes

**Se frontend já existe:**
```bash
# Identificar pasta frontend
FRONTEND_DIR=$(find . -maxdepth 2 -name "package.json" -path "*/frontend/*" -o -path "*/web/*" -o -path "*/client/*" 2>/dev/null | head -1 | xargs dirname)

# Mover para estrutura padrão
if [ -n "$FRONTEND_DIR" ]; then
  rsync -av "$FRONTEND_DIR/" frontend/ --exclude node_modules
fi
```

**Se backend já existe:**
```bash
# Identificar pasta backend
BACKEND_DIR=$(find . -maxdepth 2 \( -name "go.mod" -o -name "requirements.txt" \) -path "*/backend/*" -o -path "*/api/*" -o -path "*/server/*" 2>/dev/null | head -1 | xargs dirname)

# Mover para estrutura padrão
if [ -n "$BACKEND_DIR" ]; then
  rsync -av "$BACKEND_DIR/" backend/ --exclude node_modules --exclude __pycache__
fi
```

### Passo 2.3: Copiar Templates Base

```bash
# Usar exemplos do raijin-server como base
RAIJIN_PATH="/path/to/raijin-server"

# Copiar estrutura Kubernetes
cp -r "$RAIJIN_PATH/examples/monorepo-app/kubernetes/base/" kubernetes/base/

# Copiar overlays
cp -r "$RAIJIN_PATH/examples/monorepo-app/kubernetes/overlays/" kubernetes/overlays/

# Copiar pipeline examples
cp "$RAIJIN_PATH/examples/ci-cd/github-actions-tst.yml" .github/workflows/ci-tst.yml
cp "$RAIJIN_PATH/examples/ci-cd/github-actions-prd.yml" .github/workflows/ci-prd.yml

# Copiar Makefile
cp "$RAIJIN_PATH/examples/monorepo-app/Makefile" ./

# Copiar docker-compose template
cp "$RAIJIN_PATH/examples/monorepo-app/docker-compose.yml" ./
```

---

## Fase 3: Configurar Dockerfiles

### Passo 3.1: Detectar Tecnologia e Criar Dockerfile Frontend

**Se React/Vite:**
```bash
cat > frontend/Dockerfile <<'EOF'
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
EOF
```

**nginx.conf para SPA:**
```bash
cat > frontend/nginx.conf <<'EOF'
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    server {
        listen 80;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;

        location / {
            try_files $uri $uri/ /index.html;
        }

        location /api {
            proxy_pass http://backend:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
EOF
```

**Se Next.js:**
```bash
cat > frontend/Dockerfile <<'EOF'
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
EXPOSE 3000
CMD ["npm", "start"]
EOF
```

### Passo 3.2: Criar Dockerfile Backend

**Se Go:**
```bash
cat > backend/Dockerfile <<'EOF'
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
EOF
```

**Se Python:**
```bash
cat > backend/Dockerfile <<'EOF'
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
EOF
```

### Passo 3.3: Criar Dockerfiles de Desenvolvimento

**frontend/Dockerfile.dev:**
```bash
cat > frontend/Dockerfile.dev <<'EOF'
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
EOF
```

**backend/Dockerfile.dev:**
```bash
# Para Go com hot-reload
cat > backend/Dockerfile.dev <<'EOF'
FROM golang:1.21-alpine
RUN go install github.com/cosmtrek/air@latest
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
EXPOSE 8080
CMD ["air"]
EOF
```

---

## Fase 4: Configurar Kubernetes Manifests

### Passo 4.1: Atualizar Valores Específicos

Edite os arquivos copiados dos templates substituindo:

```bash
# Nome do projeto
PROJECT_NAME="myapp"  # Altere aqui

# Substituir em todos os YAMLs
find kubernetes/ -name "*.yaml" -type f -exec sed -i "s/myapp/$PROJECT_NAME/g" {} \;
```

### Passo 4.2: Configurar Namespace

```bash
cat > kubernetes/base/namespace.yaml <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${PROJECT_NAME}-tst
  labels:
    environment: tst
    monitoring: "true"
    istio-injection: disabled
---
apiVersion: v1
kind: Namespace
metadata:
  name: ${PROJECT_NAME}-prd
  labels:
    environment: prd
    monitoring: "true"
    istio-injection: disabled
EOF
```

### Passo 4.3: Configurar External Secrets

```bash
cat > kubernetes/base/externalsecrets.yaml <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ${PROJECT_NAME}-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: ${PROJECT_NAME}-secrets
    creationPolicy: Owner
  dataFrom:
    - extract:
        key: secret/${PROJECT_NAME}/database
    - extract:
        key: secret/${PROJECT_NAME}/api-keys
EOF
```

### Passo 4.4: Configurar Ingress

```bash
# Obter domínio do cluster
CLUSTER_DOMAIN=$(kubectl get cm -n kube-system coredns -o jsonpath='{.data.Corefile}' | grep -oP '(?<=kubernetes ).*(?= )' | head -1)

cat > kubernetes/base/ingress.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${PROJECT_NAME}-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - ${PROJECT_NAME}.${CLUSTER_DOMAIN}
      secretName: ${PROJECT_NAME}-tls
  rules:
    - host: ${PROJECT_NAME}.${CLUSTER_DOMAIN}
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
EOF
```

### Passo 4.5: Configurar recursos de Database

**Se PostgreSQL é necessário:**
```bash
cat > kubernetes/base/database/statefulset.yaml <<'EOF'
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:15-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_name
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_user
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: myapp-secrets
                  key: db_password
          volumeMounts:
            - name: postgres-storage
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: postgres-storage
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
EOF
```

### Passo 4.6: Atualizar Kustomization

```bash
cat > kubernetes/base/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespace.yaml
  - frontend/deployment.yaml
  - frontend/service.yaml
  - backend/deployment.yaml
  - backend/service.yaml
  - backend/configmap.yaml
  - database/statefulset.yaml
  - database/service.yaml
  - externalsecrets.yaml
  - ingress.yaml
EOF
```

---

## Fase 5: Configurar Overlays (TST e PRD)

### Passo 5.1: TST Overlay

```bash
cat > kubernetes/overlays/tst/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: ${PROJECT_NAME}-tst

bases:
  - ../../base

images:
  - name: harbor.local/tst/${PROJECT_NAME}-frontend
    newTag: dev-latest
  - name: harbor.local/tst/${PROJECT_NAME}-backend
    newTag: dev-latest

replicas:
  - name: frontend
    count: 1
  - name: backend
    count: 1
  - name: postgres
    count: 1

commonLabels:
  environment: tst
EOF
```

### Passo 5.2: PRD Overlay

```bash
cat > kubernetes/overlays/prd/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: ${PROJECT_NAME}-prd

bases:
  - ../../base

images:
  - name: harbor.local/prd/${PROJECT_NAME}-frontend
    newTag: v1.0.0
  - name: harbor.local/prd/${PROJECT_NAME}-backend
    newTag: v1.0.0

replicas:
  - name: frontend
    count: 3
  - name: backend
    count: 3
  - name: postgres
    count: 1

commonLabels:
  environment: prd

patches:
  - path: resources-patch.yaml
EOF
```

**Resources patch para PRD:**
```bash
cat > kubernetes/overlays/prd/resources-patch.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  template:
    spec:
      containers:
        - name: backend
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
EOF
```

---

## Fase 6: Configurar Pipeline CI/CD

### Passo 6.1: Configurar GitHub Actions (opção 1)

**Obter credenciais Harbor:**
```bash
# Criar robot account no Harbor via API ou UI
# Ou usar admin credentials
HARBOR_USER="admin"
HARBOR_PASS=$(kubectl get secret -n harbor harbor-core -o jsonpath='{.data.HARBOR_ADMIN_PASSWORD}' | base64 -d)

echo "Harbor Username: $HARBOR_USER"
echo "Harbor Password: $HARBOR_PASS"
```

**Adicionar secrets no GitHub:**
```bash
# Via GitHub CLI
gh secret set HARBOR_USERNAME -b"$HARBOR_USER"
gh secret set HARBOR_PASSWORD -b"$HARBOR_PASS"
gh secret set KUBECONFIG -b"$(cat ~/.kube/config | base64)"
```

**Atualizar .github/workflows/ci-tst.yml:**
```bash
# Substituir variáveis de ambiente
sed -i "s/myapp/${PROJECT_NAME}/g" .github/workflows/ci-tst.yml
sed -i "s/192.168.1.100:30880/${HARBOR_IP}:${HARBOR_PORT}/g" .github/workflows/ci-tst.yml
```

### Passo 6.2: Configurar Argo Workflows (opção 2)

**Criar WorkflowTemplate:**
```bash
cat > kubernetes/argo-workflow-ci.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: ${PROJECT_NAME}-ci
  namespace: argo
spec:
  arguments:
    parameters:
      - name: repo-url
        value: "https://github.com/your-org/${PROJECT_NAME}.git"
      - name: branch
        value: "develop"
      - name: image-name
        value: "${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}"
  
  templates:
    - name: main
      steps:
        - - name: checkout
            template: git-checkout
        - - name: build-frontend
            template: build-image
            arguments:
              parameters:
                - name: context
                  value: frontend
                - name: image
                  value: "${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-frontend"
        - - name: build-backend
            template: build-image
            arguments:
              parameters:
                - name: context
                  value: backend
                - name: image
                  value: "${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-backend"
    
    # Adicionar templates de build, scan, etc...
EOF
```

---

## Fase 7: Configurar Argo CD Applications

### Passo 7.1: Criar Application para TST

```bash
cat > kubernetes/argocd-app-tst.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${PROJECT_NAME}-tst
  namespace: argocd
  labels:
    environment: tst
    project: ${PROJECT_NAME}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/${PROJECT_NAME}.git
    targetRevision: develop
    path: kubernetes/overlays/tst
  
  destination:
    server: https://kubernetes.default.svc
    namespace: ${PROJECT_NAME}-tst
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
EOF
```

### Passo 7.2: Criar Application para PRD

```bash
cat > kubernetes/argocd-app-prd.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${PROJECT_NAME}-prd
  namespace: argocd
  labels:
    environment: prd
    project: ${PROJECT_NAME}
  annotations:
    notifications.argoproj.io/subscribe.on-sync-succeeded.slack: platform-alerts
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/${PROJECT_NAME}.git
    targetRevision: main
    path: kubernetes/overlays/prd
  
  destination:
    server: https://kubernetes.default.svc
    namespace: ${PROJECT_NAME}-prd
  
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
    # Manual sync only for production
EOF
```

### Passo 7.3: Aplicar Applications no Cluster

```bash
kubectl apply -f kubernetes/argocd-app-tst.yaml
kubectl apply -f kubernetes/argocd-app-prd.yaml

# Verificar status
kubectl get applications -n argocd
```

---

## Fase 8: Configurar Secrets no Vault

### Passo 8.1: Criar Script de Setup

```bash
cat > scripts/vault-setup.sh <<'EOF'
#!/bin/bash
set -e

PROJECT_NAME="${1:-myapp}"
VAULT_POD="vault-0"
VAULT_NS="vault"

echo "🔐 Configurando secrets no Vault para: $PROJECT_NAME"

# Database credentials
kubectl -n $VAULT_NS exec $VAULT_POD -- vault kv put secret/${PROJECT_NAME}/database \
  db_name=${PROJECT_NAME} \
  db_user=${PROJECT_NAME}_user \
  db_password=$(openssl rand -base64 32)

# Application secrets
kubectl -n $VAULT_NS exec $VAULT_POD -- vault kv put secret/${PROJECT_NAME}/api-keys \
  jwt_secret=$(openssl rand -base64 64) \
  api_key=$(uuidgen) \
  encryption_key=$(openssl rand -hex 32)

echo "✅ Secrets configurados!"
echo ""
echo "ExternalSecret irá sincronizar automaticamente para o namespace"
EOF

chmod +x scripts/vault-setup.sh
```

### Passo 8.2: Executar Setup

```bash
./scripts/vault-setup.sh "$PROJECT_NAME"
```

### Passo 8.3: Verificar Sincronização

```bash
# Aguardar External Secret sincronizar
sleep 10

# Verificar secret criado
kubectl get secret ${PROJECT_NAME}-secrets -n ${PROJECT_NAME}-tst
kubectl get secret ${PROJECT_NAME}-secrets -n ${PROJECT_NAME}-prd
```

---

## Fase 9: Configurar Docker Compose para Dev

### Passo 9.1: Criar docker-compose.yml

```bash
cat > docker-compose.yml <<EOF
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
    networks:
      - app-network

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
      - DB_NAME=${PROJECT_NAME}
      - DB_USER=dev
      - DB_PASSWORD=dev123
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    networks:
      - app-network

  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: ${PROJECT_NAME}
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - app-network

volumes:
  postgres_data:

networks:
  app-network:
    driver: bridge
EOF
```

---

## Fase 10: Testes e Validação

### Passo 10.1: Teste Local com Docker Compose

```bash
# Build e start
docker-compose up --build -d

# Verificar logs
docker-compose logs -f

# Aguardar serviços iniciarem
sleep 30

# Testar frontend
curl http://localhost:3000

# Testar backend
curl http://localhost:8080/health

# Parar serviços
docker-compose down
```

### Passo 10.2: Validar Kustomize

```bash
# Validar TST
kubectl kustomize kubernetes/overlays/tst > /tmp/tst-manifests.yaml
kubectl apply --dry-run=client -f /tmp/tst-manifests.yaml

# Validar PRD
kubectl kustomize kubernetes/overlays/prd > /tmp/prd-manifests.yaml
kubectl apply --dry-run=client -f /tmp/prd-manifests.yaml

echo "✅ Kustomize válido!"
```

### Passo 10.3: Deploy Manual em TST

```bash
# Primeiro build e push das imagens
docker build -t ${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-frontend:dev-latest ./frontend
docker build -t ${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-backend:dev-latest ./backend

# Login no Harbor
docker login ${HARBOR_IP}:${HARBOR_PORT} -u admin -p "${HARBOR_PASS}"

# Push imagens
docker push ${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-frontend:dev-latest
docker push ${HARBOR_IP}:${HARBOR_PORT}/tst/${PROJECT_NAME}-backend:dev-latest

# Deploy via Kustomize
kubectl apply -k kubernetes/overlays/tst

# Verificar rollout
kubectl rollout status deployment/frontend -n ${PROJECT_NAME}-tst
kubectl rollout status deployment/backend -n ${PROJECT_NAME}-tst
```

### Passo 10.4: Verificar Argo CD Sync

```bash
# Verificar Application status
kubectl get application ${PROJECT_NAME}-tst -n argocd

# Forçar sync se necessário
kubectl patch application ${PROJECT_NAME}-tst -n argocd \
  --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"syncStrategy":{"hook":{}}}}}'

# Verificar sync progress
kubectl get application ${PROJECT_NAME}-tst -n argocd -w
```

### Passo 10.5: Testar Aplicação

```bash
# Obter URL do ingress
INGRESS_URL=$(kubectl get ingress ${PROJECT_NAME}-ingress -n ${PROJECT_NAME}-tst -o jsonpath='{.spec.rules[0].host}')

# Verificar DNS
nslookup $INGRESS_URL

# Testar aplicação
curl -v https://$INGRESS_URL
curl -v https://$INGRESS_URL/api/health
```

---

## Fase 11: Documentação Final

### Passo 11.1: Criar README.md

```bash
cat > README.md <<EOF
# ${PROJECT_NAME}

Aplicação monorepo com deploy automatizado via GitOps.

## Estrutura

\`\`\`
${PROJECT_NAME}/
├── frontend/          # SPA React/Vue/Next.js
├── backend/           # API Go/Python/Node
├── kubernetes/        # Manifests K8s
│   ├── base/
│   └── overlays/{tst,prd}
├── .github/workflows/ # CI Pipelines
└── scripts/           # Utilitários
\`\`\`

## Development

\`\`\`bash
# Iniciar ambiente local
docker-compose up -d

# Acessar aplicação
open http://localhost:3000
\`\`\`

## Deploy

### TST (Auto)
\`\`\`bash
git push origin develop
# Pipeline CI/CD + Argo CD sync automático
\`\`\`

### PRD (Manual)
\`\`\`bash
git push origin main
# Aprovar sync no Argo CD UI
\`\`\`

## Secrets

Secrets gerenciados pelo Vault:

\`\`\`bash
# Configurar secrets
./scripts/vault-setup.sh ${PROJECT_NAME}

# Verificar sincronização
kubectl get secret ${PROJECT_NAME}-secrets -n ${PROJECT_NAME}-tst
\`\`\`

## Acesso

- **TST**: https://${PROJECT_NAME}-tst.local
- **PRD**: https://${PROJECT_NAME}.example.com
- **Argo CD**: https://argocd.local
- **Harbor**: https://harbor.local

EOF
```

### Passo 11.2: Criar CHANGELOG.md

```bash
cat > CHANGELOG.md <<EOF
# Changelog

## [Unreleased]

### Added
- Estrutura monorepo completa
- Pipeline CI/CD com GitHub Actions
- GitOps com Argo CD
- Secrets management com Vault
- Docker Compose para desenvolvimento local
- Kubernetes manifests com Kustomize

### Security
- Scan de vulnerabilidades com Trivy
- SAST com Semgrep
- Secrets no Vault (não em Git)

EOF
```

---

## Checklist Final

Execute esta validação automatizada:

```bash
#!/bin/bash

echo "🔍 Validando configuração do monorepo..."

checks_passed=0
checks_total=0

check() {
  ((checks_total++))
  if eval "$2"; then
    echo "✅ $1"
    ((checks_passed++))
  else
    echo "❌ $1"
  fi
}

# Estrutura de diretórios
check "Estrutura de diretórios" "test -d frontend && test -d backend && test -d kubernetes"
check "Frontend Dockerfile" "test -f frontend/Dockerfile"
check "Backend Dockerfile" "test -f backend/Dockerfile"
check "Docker Compose" "test -f docker-compose.yml"
check "Makefile" "test -f Makefile"

# Kubernetes
check "Kubernetes base" "test -d kubernetes/base"
check "Kubernetes overlays" "test -d kubernetes/overlays/tst && test -d kubernetes/overlays/prd"
check "Kustomization TST" "test -f kubernetes/overlays/tst/kustomization.yaml"
check "Kustomization PRD" "test -f kubernetes/overlays/prd/kustomization.yaml"
check "External Secrets" "test -f kubernetes/base/externalsecrets.yaml"
check "Ingress" "test -f kubernetes/base/ingress.yaml"

# CI/CD
check "GitHub Actions TST" "test -f .github/workflows/ci-tst.yml"
check "GitHub Actions PRD" "test -f .github/workflows/ci-prd.yml"
check "Argo CD App TST" "test -f kubernetes/argocd-app-tst.yaml"
check "Argo CD App PRD" "test -f kubernetes/argocd-app-prd.yaml"

# Scripts
check "Vault setup script" "test -x scripts/vault-setup.sh"

# Documentação
check "README.md" "test -f README.md"
check "CHANGELOG.md" "test -f CHANGELOG.md"

echo ""
echo "📊 Resultado: $checks_passed/$checks_total checks passed"

if [ $checks_passed -eq $checks_total ]; then
  echo "🎉 Configuração completa!"
  exit 0
else
  echo "⚠️  Alguns checks falharam. Revise a configuração."
  exit 1
fi
```

---

## Próximos Passos

1. **Push para Git**:
   ```bash
   git add .
   git commit -m "Setup monorepo with ArgoCD integration"
   git push origin develop
   ```

2. **Monitorar Pipeline**:
   ```bash
   # GitHub Actions
   gh run watch
   
   # Argo Workflows
   argo watch -n argo
   ```

3. **Verificar Deploy**:
   ```bash
   kubectl get applications -n argocd
   kubectl get pods -n ${PROJECT_NAME}-tst
   ```

4. **Configurar Monitoring**:
   - Adicionar ServiceMonitor para Prometheus
   - Configurar dashboards no Grafana
   - Configurar alertas

5. **Security Hardening**:
   - Habilitar Network Policies
   - Configurar Pod Security Standards
   - Configurar RBAC

---

## Troubleshooting

### Imagem não puxa do Harbor

```bash
# Verificar se Harbor está acessível
curl -k https://${HARBOR_IP}:${HARBOR_PORT}

# Verificar secret de pull
kubectl get secret -n ${PROJECT_NAME}-tst | grep harbor

# Criar secret se necessário
kubectl create secret docker-registry harbor-secret \
  --docker-server=${HARBOR_IP}:${HARBOR_PORT} \
  --docker-username=admin \
  --docker-password=${HARBOR_PASS} \
  -n ${PROJECT_NAME}-tst
```

### Argo CD não sincroniza

```bash
# Verificar logs do Argo CD
kubectl logs -n argocd deployment/argocd-application-controller

# Forçar refresh
kubectl patch application ${PROJECT_NAME}-tst -n argocd \
  --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

### External Secret não cria secret

```bash
# Verificar External Secret status
kubectl describe externalsecret ${PROJECT_NAME}-secrets -n ${PROJECT_NAME}-tst

# Verificar ClusterSecretStore
kubectl get clustersecretstore vault-backend -o yaml

# Verificar Vault accessibility
kubectl exec -n vault vault-0 -- vault status
```

---

## Referências

- [Argo CD Documentation](https://argo-cd.readthedocs.io/)
- [Kustomize](https://kustomize.io/)
- [External Secrets Operator](https://external-secrets.io/)
- [Harbor Documentation](https://goharbor.io/docs/)
- Exemplos: `/examples/monorepo-app/` e `/examples/ci-cd/`
