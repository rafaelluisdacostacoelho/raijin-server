# Exemplo Prático: Publicar E-commerce na Produção

Este documento mostra um exemplo real de como **publicar um novo aplicativo** (e-commerce) na infraestrutura raijin-server já configurada.

---

## 📋 Cenário

**Situação**: Você tem um servidor Kubernetes configurado com raijin-server e quer publicar um novo e-commerce.

**Infraestrutura Existente** ✅:
- Kubernetes (K3s) rodando
- ArgoCD instalado
- Harbor registry configurado
- Vault gerenciando secrets
- Traefik ingress com SSL
- Prometheus + Grafana monitorando

**Novo Projeto a Publicar**:
- Nome: E-commerce Platform
- Frontend: Next.js 14 (TypeScript)
- Backend: Go 1.21 + Fiber
- Database: PostgreSQL 15
- Cache: Redis
- Storage: MinIO (já instalado)
- Domínio: shop.example.com

**Objetivo**: Publicar esse app na internet via CI/CD automático

---

## 🎯 Passo 1: Escolher o Guia

Situação: Primeira vez configurando monorepo + equipe com conhecimento intermediário

**Decisão**: Usar [COPILOT_PROMPT.md](COPILOT_PROMPT.md) com Copilot Chat

---

## 🤖 Passo 2: Preparar o Prompt

### 2.1: Abrir Copilot Chat

```
Ctrl+Shift+I (ou Cmd+Shift+I no macOS)
```

### 2.2: Cole o Prompt Base

```
Baseado no guia @docs/ci-cd/COPILOT_PROMPT.md, configure um monorepo completo para:

PROJETO: ecommerce-platform

TECNOLOGIAS:
- Frontend: Next.js 14 com TypeScript, Tailwind CSS, shadcn/ui
- Backend: Go 1.21 com Fiber framework, GORM
- Database: PostgreSQL 15 com extensões (uuid, pgcrypto)
- Cache: Redis 7 para sessions e cart
- Storage: MinIO para product images
- Email: SMTP integration (SendGrid)
- Payment: Stripe integration

INFRAESTRUTURA RAIJIN:
- Harbor Registry: 192.168.1.100:30880
- Vault: http://vault.local
- ArgoCD: https://argocd.local
- Domain TST: ecommerce-tst.local
- Domain PRD: shop.example.com

ESTRUTURA BACKEND:
backend/
├── cmd/
│   └── server/
│       └── main.go
├── internal/
│   ├── api/
│   │   ├── handlers/
│   │   ├── middleware/
│   │   └── routes/
│   ├── models/
│   ├── services/
│   └── repository/
├── pkg/
│   ├── config/
│   ├── database/
│   └── redis/
├── go.mod
└── go.sum

FEATURES NECESSÁRIAS:
- User authentication (JWT)
- Product catalog with images
- Shopping cart (Redis)
- Order processing
- Payment integration
- Email notifications
- Admin dashboard

SECRETS VAULT:
- Database credentials
- Redis password
- MinIO access keys
- Stripe API keys
- SendGrid API key
- JWT signing secret

REQUIREMENTS:
1. Dockerfiles multi-stage otimizados
2. Kubernetes manifests com health checks
3. HPA para backend (min: 2, max: 10)
4. Resource limits definidos
5. Network policies (backend pode acessar DB, Redis, MinIO)
6. PVC para PostgreSQL (50Gi)
7. Ingress com TLS (cert-manager)
8. ServiceMonitor para Prometheus
9. GitHub Actions pipeline com:
   - Semgrep SAST
   - Go tests + coverage
   - Next.js build
   - Trivy scan
   - Harbor push
   - Kustomize update

Crie TODA a estrutura com arquivos completos e funcionais.
```

---

## 📂 Passo 3: Revisar Estrutura Gerada

O Copilot deve gerar esta estrutura:

```
ecommerce-platform/
├── .github/
│   └── workflows/
│       ├── ci-tst.yml
│       └── ci-prd.yml
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   ├── package.json
│   ├── tsconfig.json
│   └── next.config.js
├── backend/
│   ├── cmd/server/main.go
│   ├── internal/
│   ├── pkg/
│   ├── tests/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   ├── go.mod
│   └── go.sum
├── kubernetes/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── frontend/
│   │   ├── backend/
│   │   ├── postgres/
│   │   ├── redis/
│   │   ├── minio/
│   │   ├── externalsecrets.yaml
│   │   ├── networkpolicy.yaml
│   │   └── ingress.yaml
│   ├── overlays/
│   │   ├── tst/
│   │   └── prd/
│   ├── argocd-app-tst.yaml
│   └── argocd-app-prd.yaml
├── scripts/
│   ├── vault-setup.sh
│   ├── dev.sh
│   └── db-migrate.sh
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## 🐳 Passo 4: Validar Dockerfiles

### Frontend (Next.js)

Verificar se o Dockerfile tem:
- ✅ Multi-stage build
- ✅ Node.js 20 alpine
- ✅ npm ci (não npm install)
- ✅ Standalone output
- ✅ Non-root user

### Backend (Go)

Verificar se o Dockerfile tem:
- ✅ Multi-stage build
- ✅ Go 1.21
- ✅ CGO_ENABLED=0
- ✅ Alpine ou distroless base
- ✅ CA certificates
- ✅ Non-root user

---

## ☸️ Passo 5: Validar Kubernetes Manifests

### 5.1: Testar Kustomize

```bash
cd ecommerce-platform

# Validar TST
kubectl kustomize kubernetes/overlays/tst > /tmp/tst.yaml
kubectl apply --dry-run=client -f /tmp/tst.yaml

# Validar PRD
kubectl kustomize kubernetes/overlays/prd > /tmp/prd.yaml
kubectl apply --dry-run=client -f /tmp/prd.yaml
```

### 5.2: Verificar Resource Limits

```bash
# Check se todos os containers têm limits
grep -r "resources:" kubernetes/base/ -A 5
```

Deve ter:
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```

### 5.3: Verificar Health Checks

```bash
# Check liveness e readiness probes
grep -r "livenessProbe:" kubernetes/base/ -A 5
grep -r "readinessProbe:" kubernetes/base/ -A 5
```

---

## 🔐 Passo 6: Configurar Secrets no Vault

### 6.1: Adaptar Script

```bash
chmod +x scripts/vault-setup.sh
```

Verifique se o script cria:
- `secret/ecommerce/database`
- `secret/ecommerce/redis`
- `secret/ecommerce/minio`
- `secret/ecommerce/stripe`
- `secret/ecommerce/sendgrid`
- `secret/ecommerce/jwt`

### 6.2: Executar Setup

```bash
./scripts/vault-setup.sh
```

### 6.3: Validar Secrets

```bash
kubectl -n vault exec vault-0 -- vault kv list secret/ecommerce
```

Output esperado:
```
Keys
----
database
jwt
minio
redis
sendgrid
stripe
```

---

## 🧪 Passo 7: Testar Localmente

### 7.1: Docker Compose

```bash
# Build e start
docker-compose up --build -d

# Verificar logs
docker-compose logs -f

# Aguardar inicialização
sleep 30
```

### 7.2: Testar Endpoints

```bash
# Frontend
curl http://localhost:3000
# Deve retornar HTML do Next.js

# Backend health
curl http://localhost:8080/health
# {"status":"ok","database":"connected","redis":"connected"}

# Backend API
curl http://localhost:8080/api/v1/products
# []
```

### 7.3: Verificar Database

```bash
docker-compose exec postgres psql -U ecommerce -d ecommerce -c "\dt"
```

Deve mostrar tabelas: users, products, orders, etc.

### 7.4: Parar Ambiente

```bash
docker-compose down
```

---

## 🚢 Passo 8: Deploy em TST

### 8.1: Build e Push Imagens

```bash
# Variáveis
HARBOR_REGISTRY="192.168.1.100:30880"
PROJECT="tst"

# Login Harbor
docker login $HARBOR_REGISTRY
# user: admin
# password: [obtido do Vault ou kubectl]

# Build Frontend
docker build -t $HARBOR_REGISTRY/$PROJECT/ecommerce-frontend:dev-v1 ./frontend
docker push $HARBOR_REGISTRY/$PROJECT/ecommerce-frontend:dev-v1

# Build Backend
docker build -t $HARBOR_REGISTRY/$PROJECT/ecommerce-backend:dev-v1 ./backend
docker push $HARBOR_REGISTRY/$PROJECT/ecommerce-backend:dev-v1
```

### 8.2: Atualizar Kustomize

Editar `kubernetes/overlays/tst/kustomization.yaml`:

```yaml
images:
  - name: harbor.local/tst/ecommerce-frontend
    newName: 192.168.1.100:30880/tst/ecommerce-frontend
    newTag: dev-v1
  - name: harbor.local/tst/ecommerce-backend
    newName: 192.168.1.100:30880/tst/ecommerce-backend
    newTag: dev-v1
```

### 8.3: Deploy Manual

```bash
# Apply manifests
kubectl apply -k kubernetes/overlays/tst

# Verificar criação de recursos
kubectl get all -n ecommerce-tst

# Aguardar pods ficarem ready
kubectl wait --for=condition=ready pod -l app=frontend -n ecommerce-tst --timeout=300s
kubectl wait --for=condition=ready pod -l app=backend -n ecommerce-tst --timeout=300s
```

### 8.4: Verificar Logs

```bash
# Frontend
kubectl logs -n ecommerce-tst -l app=frontend --tail=50

# Backend
kubectl logs -n ecommerce-tst -l app=backend --tail=50

# PostgreSQL
kubectl logs -n ecommerce-tst -l app=postgres --tail=50
```

---

## 🔄 Passo 9: Configurar Argo CD

### 9.1: Criar Applications

```bash
kubectl apply -f kubernetes/argocd-app-tst.yaml
kubectl apply -f kubernetes/argocd-app-prd.yaml
```

### 9.2: Verificar Status

```bash
kubectl get applications -n argocd

# Deve mostrar:
# NAME              SYNC STATUS   HEALTH STATUS
# ecommerce-tst     Synced        Healthy
# ecommerce-prd     OutOfSync     Healthy
```

### 9.3: Acessar UI do Argo CD

```bash
# Obter senha
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# Port-forward
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Abrir browser
open https://localhost:8080
# User: admin
# Pass: [obtido acima]
```

### 9.4: Verificar Sync

Na UI do Argo CD:
1. Selecione `ecommerce-tst`
2. Verifique se está "Synced" e "Healthy"
3. Clique em "App Details" → "Events"
4. Verifique último sync

---

## 🌐 Passo 10: Configurar Ingress e DNS

### 10.1: Verificar Ingress

```bash
kubectl get ingress -n ecommerce-tst

# Deve mostrar:
# NAME                 HOSTS                  ADDRESS         PORTS
# ecommerce-ingress    ecommerce-tst.local    192.168.1.100   80,443
```

### 10.2: Configurar DNS Local

```bash
# Adicionar ao /etc/hosts (Linux/Mac)
echo "192.168.1.100 ecommerce-tst.local" | sudo tee -a /etc/hosts

# Ou configurar no DNS do Kubernetes (ver INTERNAL_DNS.md)
```

### 10.3: Testar Acesso

```bash
# Frontend
curl -k https://ecommerce-tst.local
# Deve retornar HTML do Next.js

# Backend API
curl -k https://ecommerce-tst.local/api/health
# {"status":"ok"}
```

### 10.4: Verificar Certificado TLS

```bash
# Verificar secret criado pelo cert-manager
kubectl get certificate -n ecommerce-tst

# Detalhes do certificado
kubectl describe certificate ecommerce-tls -n ecommerce-tst
```

---

## 🤖 Passo 11: Configurar GitHub Actions

### 11.1: Adicionar Secrets no GitHub

```bash
# Via GitHub CLI
gh secret set HARBOR_REGISTRY -b"192.168.1.100:30880"
gh secret set HARBOR_USERNAME -b"admin"
gh secret set HARBOR_PASSWORD -b"<password>"

# Kubeconfig (para deploy direto, se necessário)
gh secret set KUBECONFIG -b"$(cat ~/.kube/config | base64)"
```

### 11.2: Commit e Push

```bash
git init
git add .
git commit -m "Initial commit: ecommerce platform monorepo"
git branch -M main
git remote add origin https://github.com/your-org/ecommerce-platform.git
git push -u origin main

# Criar branch develop
git checkout -b develop
git push -u origin develop
```

### 11.3: Testar Pipeline

```bash
# Fazer mudança em develop
echo "// Test change" >> frontend/app/page.tsx
git add .
git commit -m "test: trigger CI/CD pipeline"
git push origin develop

# Monitorar pipeline
gh run watch
```

### 11.4: Verificar Resultados

Pipeline deve executar:
1. ✅ Semgrep SAST scan
2. ✅ Frontend build (Next.js)
3. ✅ Backend tests (Go)
4. ✅ Docker build
5. ✅ Trivy vulnerability scan
6. ✅ Push para Harbor
7. ✅ Update Kustomize image tag
8. ✅ Commit and push (trigger Argo CD sync)

---

## 📊 Passo 12: Configurar Monitoring

### 12.1: Verificar ServiceMonitor

```bash
kubectl get servicemonitor -n ecommerce-tst
```

### 12.2: Verificar Métricas no Prometheus

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus-k8s 9090:9090

# Abrir browser
open http://localhost:9090

# Query exemplo:
# rate(http_requests_total{namespace="ecommerce-tst"}[5m])
```

### 12.3: Configurar Dashboard Grafana

```bash
# Port-forward Grafana
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Abrir browser
open http://localhost:3000

# User/Pass: admin/admin (alterar na primeira vez)
```

Importar dashboards:
- ID 6417: Kubernetes Cluster Monitoring
- ID 7249: Kubernetes Deployment
- Custom: Backend API metrics

---

## ✅ Checklist Final

- [x] Estrutura monorepo criada
- [x] Dockerfiles funcionais
- [x] Docker Compose testado localmente
- [x] Kubernetes manifests válidos
- [x] Secrets configurados no Vault
- [x] External Secrets sincronizando
- [x] Deploy manual em TST OK
- [x] Pods healthy
- [x] Argo CD Applications criadas
- [x] Ingress acessível
- [x] TLS funcionando
- [x] GitHub Actions pipeline configurado
- [x] Pipeline executando com sucesso
- [x] Monitoring Prometheus/Grafana
- [x] Logs centralizados (Loki)

---

## 🎉 Resultado Final

### URLs de Acesso

```
Frontend TST:  https://ecommerce-tst.local
Backend API:   https://ecommerce-tst.local/api
Argo CD:       https://argocd.local
Harbor:        https://harbor.local
Prometheus:    (port-forward) http://localhost:9090
Grafana:       (port-forward) http://localhost:3000
```

### Workflow GitOps

```
Developer push to develop
         ↓
GitHub Actions CI
  - Build & Test
  - Scan (Semgrep + Trivy)
  - Push to Harbor
  - Update Kustomize
         ↓
Argo CD detects change
  - Auto-sync enabled
  - Apply manifests
  - Health check
         ↓
Application deployed to TST
  - Pods running
  - Ingress routing
  - Monitoring active
```

### Próximos Passos

1. **Configurar PRD**:
   - Ajustar `kubernetes/overlays/prd/`
   - Deploy via Argo CD (manual sync)
   - Configurar domínio real

2. **Melhorias de Segurança**:
   - Network Policies
   - Pod Security Standards
   - RBAC detalhado

3. **Performance**:
   - HPA (Horizontal Pod Autoscaler)
   - Cache optimizations
   - CDN para assets

4. **Observability**:
   - Custom dashboards Grafana
   - Alerting rules
   - Distributed tracing

---

## 📚 Referências Usadas

- [COPILOT_PROMPT.md](COPILOT_PROMPT.md) - Prompt base
- [AGENT_GUIDE.md](AGENT_GUIDE.md) - Comandos técnicos
- [examples/monorepo-app/](../../examples/monorepo-app/) - Estrutura de referência
- [examples/ci-cd/](../../examples/ci-cd/) - Pipeline examples

---

**Tempo estimado total**: 4-6 horas (primeira vez), 2-3 horas (experiente)

**Dificuldade**: Intermediária

**Requer conhecimento prévio**: Kubernetes básico, Docker, Git
