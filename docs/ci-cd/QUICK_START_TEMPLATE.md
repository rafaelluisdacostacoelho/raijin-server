# Quick Start: Publicar Novo App no Kubernetes

> 📋 Template rápido para publicar aplicativos na infraestrutura raijin-server

---

## Prompt para Copilot/Agent

```
Publique meu aplicativo no Kubernetes produtivo com CI/CD:

CONTEXTO:
- Infraestrutura raijin-server JÁ CONFIGURADA ✅
- Kubernetes K3s rodando ✅
- ArgoCD instalado ✅
- Harbor registry: 192.168.1.100:30880 ✅
- Vault para secrets ✅
- Traefik ingress com SSL ✅

MEU APLICATIVO:
- Nome: [nome-do-app]
- Tipo: [Website/API/SPA/Full-stack]
- Frontend: [React/Vue/Next.js/Angular ou N/A]
- Backend: [Go/Python/Node.js/Java ou N/A]
- Database: [PostgreSQL/MySQL/MongoDB/Redis ou N/A]
- Domínio: [app.example.com]

REQUISITOS:
1. Dockerfiles otimizados (multi-stage)
2. Kubernetes manifests (Deployment, Service, Ingress)
3. Pipeline CI/CD (GitHub Actions preferred)
4. Argo CD Application para deploy automático
5. Secrets no Vault (não no Git!)
6. SSL/HTTPS automático (cert-manager)
7. Monitoring (ServiceMonitor para Prometheus)

OUTPUTS:
- App rodando em produção
- Acessível via HTTPS: https://app.example.com
- Deploy automático ao push no GitHub
- Métricas no Grafana

Execute configuração completa.
```

---

## Variáveis de Configuração

Ajuste estas variáveis antes de iniciar:

```bash
# Seu App
export APP_NAME="myapp"
export APP_DOMAIN="myapp.example.com"
export GIT_REPO="https://github.com/your-org/myapp.git"

# Infraestrutura raijin-server (já configurada)
export HARBOR_IP="192.168.1.100"
export HARBOR_PORT="30880"
export HARBOR_REGISTRY="${HARBOR_IP}:${HARBOR_PORT}"

# Ambientes
export DOMAIN_TST="${APP_NAME}-tst.local"
export DOMAIN_PRD="${APP_DOMAIN}"

# Kubernetes
export NS_TST="${APP_NAME}-tst"
export NS_PRD="${APP_NAME}-prd"
```

---

## Comandos Rápidos

### 1. Setup Inicial

```bash
# Clone template base
git clone https://github.com/your-org/raijin-server.git /tmp/raijin
cp -r /tmp/raijin/examples/monorepo-app/* .

# Substituir placeholders
find . -type f -exec sed -i "s/myapp/${PROJECT_NAME}/g" {} \;
find . -type f -exec sed -i "s/192.168.1.100:30880/${HARBOR_REGISTRY}/g" {} \;
```

### 2. Build Local

```bash
# Docker Compose
docker-compose up --build -d
docker-compose logs -f

# Testes
curl http://localhost:3000  # Frontend
curl http://localhost:8080/health  # Backend
```

### 3. Deploy TST

```bash
# Configurar secrets
./scripts/vault-setup.sh ${PROJECT_NAME}

# Build e push imagens
docker build -t ${HARBOR_REGISTRY}/tst/${PROJECT_NAME}-frontend:dev-latest ./frontend
docker build -t ${HARBOR_REGISTRY}/tst/${PROJECT_NAME}-backend:dev-latest ./backend
docker login ${HARBOR_REGISTRY}
docker push ${HARBOR_REGISTRY}/tst/${PROJECT_NAME}-frontend:dev-latest
docker push ${HARBOR_REGISTRY}/tst/${PROJECT_NAME}-backend:dev-latest

# Deploy
kubectl apply -k kubernetes/overlays/tst
kubectl rollout status deployment/frontend -n ${NS_TST}
kubectl rollout status deployment/backend -n ${NS_TST}
```

### 4. Configurar Argo CD

```bash
# Criar Applications
kubectl apply -f kubernetes/argocd-app-tst.yaml
kubectl apply -f kubernetes/argocd-app-prd.yaml

# Verificar
kubectl get applications -n argocd
kubectl get application ${PROJECT_NAME}-tst -n argocd -o yaml
```

### 5. Verificar Deploy

```bash
# Pods
kubectl get pods -n ${NS_TST}

# Logs
kubectl logs -n ${NS_TST} -l app=frontend --tail=50
kubectl logs -n ${NS_TST} -l app=backend --tail=50

# Secrets
kubectl get secret ${PROJECT_NAME}-secrets -n ${NS_TST}

# Ingress
kubectl get ingress -n ${NS_TST}
```

---

## Estrutura Mínima Necessária

```
myapp/
├── .github/
│   └── workflows/
│       ├── ci-tst.yml
│       └── ci-prd.yml
├── frontend/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   ├── nginx.conf
│   └── src/
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── {cmd/,internal/} ou {src/,main.py}
├── kubernetes/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── frontend/{deployment,service}.yaml
│   │   ├── backend/{deployment,service}.yaml
│   │   ├── externalsecrets.yaml
│   │   └── ingress.yaml
│   └── overlays/
│       ├── tst/kustomization.yaml
│       └── prd/kustomization.yaml
├── scripts/
│   └── vault-setup.sh
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## Checklist Rápido

- [ ] Estrutura de diretórios criada
- [ ] Dockerfiles (multi-stage)
- [ ] Kubernetes base manifests
- [ ] Kustomize overlays (tst/prd)
- [ ] External Secrets configurado
- [ ] Pipeline CI (GitHub Actions ou Argo Workflows)
- [ ] Argo CD Applications criadas
- [ ] Secrets configurados no Vault
- [ ] Docker-compose funcional
- [ ] Makefile com comandos
- [ ] README.md documentado
- [ ] Deploy em TST OK
- [ ] Ingress acessível
- [ ] Monitoring labels

---

## Troubleshooting Comum

### Pods não iniciam

```bash
kubectl describe pod <pod-name> -n ${NS_TST}
kubectl logs <pod-name> -n ${NS_TST}
```

### ImagePullBackOff

```bash
# Verificar secret
kubectl get secret -n ${NS_TST} | grep harbor

# Recriar secret
kubectl create secret docker-registry harbor-pull \
  --docker-server=${HARBOR_REGISTRY} \
  --docker-username=admin \
  --docker-password=<password> \
  -n ${NS_TST}

# Adicionar no deployment
spec:
  imagePullSecrets:
    - name: harbor-pull
```

### Argo CD OutOfSync

```bash
# Refresh
argocd app get ${PROJECT_NAME}-tst --refresh

# Diff
argocd app diff ${PROJECT_NAME}-tst

# Sync
argocd app sync ${PROJECT_NAME}-tst
```

---

## Templates Mínimos

### Dockerfile Frontend (React)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Dockerfile Backend (Go)

```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o server ./cmd

FROM alpine:latest
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/server .
EXPOSE 8080
CMD ["./server"]
```

### Kustomization Base

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - frontend/deployment.yaml
  - frontend/service.yaml
  - backend/deployment.yaml
  - backend/service.yaml
  - externalsecrets.yaml
  - ingress.yaml
```

### Kustomization Overlay TST

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
```

### Argo CD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-tst
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/repo.git
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
```

### External Secret

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
  dataFrom:
    - extract:
        key: secret/myapp/database
```

### GitHub Actions CI

```yaml
name: CI/CD TST
on:
  push:
    branches: [develop]
env:
  HARBOR_REGISTRY: 192.168.1.100:30880
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/login-action@v2
        with:
          registry: ${{ env.HARBOR_REGISTRY }}
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_PASSWORD }}
      - uses: docker/build-push-action@v4
        with:
          context: ./frontend
          push: true
          tags: ${{ env.HARBOR_REGISTRY }}/tst/myapp-frontend:dev-${{ github.sha }}
```

---

## Comandos One-Liner

```bash
# Build all
docker-compose build && docker-compose push

# Deploy TST
kubectl apply -k kubernetes/overlays/tst && kubectl rollout status -n myapp-tst deploy/frontend deploy/backend

# Logs all
kubectl logs -n myapp-tst -l app=frontend --tail=100 & kubectl logs -n myapp-tst -l app=backend --tail=100

# Port forward
kubectl port-forward -n myapp-tst svc/frontend 8080:80 & kubectl port-forward -n myapp-tst svc/backend 8081:8080

# Delete all
kubectl delete -k kubernetes/overlays/tst
```

---

## Referências Rápidas

| Componente | Documentação | Port |
|------------|--------------|------|
| Argo CD | https://argo-cd.readthedocs.io | 8080 |
| Harbor | https://goharbor.io/docs | 30880 |
| Vault | https://www.vaultproject.io/docs | 8200 |
| Traefik | https://doc.traefik.io/traefik | 80/443 |
| External Secrets | https://external-secrets.io | - |

---

## Scripts Úteis

### vault-setup.sh

```bash
#!/bin/bash
PROJECT=${1:-myapp}
kubectl -n vault exec vault-0 -- vault kv put secret/$PROJECT/database \
  db_password=$(openssl rand -base64 32)
kubectl -n vault exec vault-0 -- vault kv put secret/$PROJECT/api-keys \
  jwt_secret=$(openssl rand -base64 64)
```

### Makefile

```makefile
.PHONY: dev build deploy-tst
dev:
	docker-compose up -d
build:
	docker build -t $(PROJECT)-frontend ./frontend
	docker build -t $(PROJECT)-backend ./backend
deploy-tst:
	kubectl apply -k kubernetes/overlays/tst
```

---

Para mais detalhes, consulte:
- **Prompt completo**: [COPILOT_PROMPT.md](COPILOT_PROMPT.md)
- **Guia do agente**: [AGENT_GUIDE.md](AGENT_GUIDE.md)
- **Exemplos**: `examples/monorepo-app/` e `examples/ci-cd/`
