# CI/CD Pipeline Examples

Exemplos de pipelines integrando Semgrep + Trivy + Harbor + Vault para diferentes plataformas de CI/CD.

## Estrutura

```
examples/ci-cd/
├── README.md (este arquivo)
├── github-actions-tst.yml     # GitHub Actions - TST environment
├── github-actions-prd.yml     # GitHub Actions - PRD environment
├── argocd-application.yaml    # Argo CD - GitOps Applications
├── argo-workflow-ci.yaml      # Argo Workflows - CI Pipeline
├── externalsecret-argo.yaml   # External Secrets para Argo
└── semgrep-rules.yml          # Custom Semgrep rules

```

## Arquitetura CI/CD

### GitOps com Argo CD + Argo Workflows

```
┌─────────────────────────────────────────────────────────────────┐
│                     GIT REPOSITORY                               │
│  app-repo/                  infra-repo/                         │
│  ├── src/                   ├── kubernetes/                     │
│  ├── Dockerfile             │   ├── base/                       │
│  └── tests/                 │   ├── overlays/tst/               │
│                             │   └── overlays/prd/               │
└─────────────────┬───────────────────┬───────────────────────────┘
                  │                   │
                  ▼                   ▼
         ┌────────────────┐  ┌────────────────┐
         │ Argo Workflows │  │   Argo CD      │
         │ (CI Pipeline)  │  │  (GitOps CD)   │
         │                │  │                │
         │ 1. Build       │  │ 1. Sync Git    │
         │ 2. Test        │  │ 2. Apply K8s   │
         │ 3. Scan        │  │ 3. Health      │
         │ 4. Push Harbor │──│ 4. Rollback    │
         └────────────────┘  └────────────────┘
```

### Fluxo TST (Staging)
```
git push develop
  ↓
[Argo Workflows - CI]
  ├── Semgrep SAST → Warning only
  ├── Unit Tests → Must pass
  ├── Docker Build (Kaniko)
  ├── Trivy Scan → Warning only
  └── Push Harbor tst/
  ↓
[Argo CD - GitOps]
  ├── Detect image change
  ├── Auto-sync to K8s
  └── Health check
  ↓
[Slack Notification]
```

### Fluxo PRD (Production)
```
git push main
  ↓
[Argo Workflows - CI]
  ├── Semgrep SAST → Block if ERROR
  ├── Full Test Suite → Must pass
  ├── Docker Build (Kaniko)
  ├── Trivy Scan → Block if CRITICAL
  └── Push Harbor prd/
  ↓
[Argo CD - GitOps]
  ├── Manual Sync Required
  ├── Apply with diff preview
  └── Progressive rollout
  ↓
[Slack Notification + Tag]
```

## Secrets Management

Todos os exemplos usam Vault + External Secrets Operator:

```bash
# Armazenar credenciais no Vault
kubectl -n vault exec vault-0 -- vault kv put secret/cicd/harbor \
  username=robot$cicd \
  password=<HARBOR_TOKEN>

kubectl -n vault exec vault-0 -- vault kv put secret/cicd/github \
  token=<GITHUB_TOKEN> \
  webhook-secret=<WEBHOOK_SECRET>

kubectl -n vault exec vault-0 -- vault kv put secret/cicd/argocd \
  admin-password=<ARGOCD_PASSWORD>

# ExternalSecret sincroniza automaticamente
kubectl apply -f externalsecret-argo.yaml
```

## Configuração por Plataforma

### Argo CD + Argo Workflows (Recomendado)

**Setup**:
1. Instalar via raijin-server:
   ```bash
   sudo raijin-server -m argo
   ```

2. Configurar secrets no Vault:
   ```bash
   vault kv put secret/cicd/harbor username=robot password=<token>
   vault kv put secret/cicd/github token=<pat>
   ```

3. Aplicar ExternalSecrets:
   ```bash
   kubectl apply -f externalsecret-argo.yaml
   ```

4. Criar Application no Argo CD:
   ```bash
   kubectl apply -f argocd-application.yaml
   ```

5. Criar WorkflowTemplate no Argo Workflows:
   ```bash
   kubectl apply -f argo-workflow-ci.yaml
   ```

**Ver**: `argocd-application.yaml`, `argo-workflow-ci.yaml`, `externalsecret-argo.yaml`

**Acesso**:
- Argo CD UI: https://argocd.local ou http://<node-ip>:30443
- Argo Workflows UI: https://argo.local ou http://<node-ip>:30881

---

### GitHub Actions

**Setup**:
1. Adicionar secrets no repositório: Settings → Secrets and variables → Actions
   - `HARBOR_USERNAME`: `robot$cicd-tst` ou `robot$cicd-prd`
   - `HARBOR_PASSWORD`: Token do robot account
   - `KUBECONFIG`: Base64 do kubeconfig (para deploy)

2. Adicionar workflows na pasta `.github/workflows/`:
   - `ci-tst.yml` (develop branch)
   - `ci-prd.yml` (main branch)

**Ver**: `github-actions-tst.yml`, `github-actions-prd.yml`

## Semgrep Configuration

### Rules Auto (Recomendado)

```bash
semgrep --config=auto .
```

Inclui:
- Security rules (OWASP Top 10)
- Best practices por linguagem
- Common bugs

### Rules Customizadas

Ver: `semgrep-rules.yml`

Adicionar no pipeline:
```bash
semgrep --config=semgrep-rules.yml .
```

### Ignoring False Positives

**No código**:
```python
# nosemgrep: python.lang.security.audit.dangerous-spawn.dangerous-spawn
os.system(user_input)  # Safe because user_input is validated
```

**No arquivo `.semgrepignore`**:
```
tests/
vendor/
node_modules/
*.test.js
```

---

## Trivy Configuration

### TST (Warning Only)

```bash
trivy image \
  --severity HIGH,CRITICAL \
  --exit-code 0 \
  --format json \
  harbor.asgard:30880/tst/myapp:dev-123
```

### PRD (Blocking)

```bash
trivy image \
  --severity CRITICAL \
  --exit-code 1 \
  harbor.asgard:30880/prd/myapp:v1.0.0
```

### Ignorar CVEs Específicos

```bash
# .trivyignore
CVE-2024-12345  # False positive - not exploitable
CVE-2024-67890  # Will be fixed in next release
```

---

## Harbor Integration

### Login

```bash
echo $HARBOR_PASSWORD | docker login 192.168.1.100:30880 \
  -u $HARBOR_USERNAME --password-stdin
```

### Tag and Push

**TST**:
```bash
docker tag myapp:latest 192.168.1.100:30880/tst/myapp:dev-${BUILD_ID}
docker push 192.168.1.100:30880/tst/myapp:dev-${BUILD_ID}
```

**PRD**:
```bash
docker tag myapp:latest 192.168.1.100:30880/prd/myapp:v${VERSION}
docker push 192.168.1.100:30880/prd/myapp:v${VERSION}
```

### Verificar Scan Status

```bash
# Via API
curl -u $HARBOR_USERNAME:$HARBOR_PASSWORD \
  "http://192.168.1.100:30880/api/v2.0/projects/prd/repositories/myapp/artifacts/v1.0.0/additions/vulnerabilities"
```

---

## Kubernetes Deployment

### Obter Secrets do Vault (via ESO)

```yaml
# ExternalSecret já sincroniza automaticamente
# Secret disponível como K8s Secret nativo
apiVersion: v1
kind: Secret
metadata:
  name: myapp-secrets
  namespace: production
type: Opaque
data:
  DB_PASSWORD: <synced-from-vault>
  API_KEY: <synced-from-vault>
```

### Deploy

**TST**:
```bash
kubectl set image deployment/myapp \
  myapp=192.168.1.100:30880/tst/myapp:dev-123 \
  -n tst

kubectl rollout status deployment/myapp -n tst --timeout=5m
```

**PRD** (Blue-Green):
```bash
# Deploy green
kubectl apply -f k8s/prd/deployment-green.yaml

# Wait for ready
kubectl rollout status deployment/myapp-green -n prd --timeout=10m

# Switch traffic
kubectl patch service myapp -n prd \
  -p '{"spec":{"selector":{"version":"green"}}}'

# Cleanup blue
kubectl delete deployment myapp-blue -n prd
```

---

## Monitoring & Notifications

### Slack Webhook

```bash
# Notify success
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "✅ Deploy PRD Success: myapp v1.0.0",
    "username": "Harness Bot",
    "icon_emoji": ":rocket:"
  }'

# Notify failure
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "❌ Deploy PRD Failed: myapp v1.0.0\nReason: Trivy found CRITICAL vulnerabilities",
    "username": "Harness Bot",
    "icon_emoji": ":x:"
  }'
```

### Email (via Alertmanager)

Configurado no Prometheus Alertmanager para alertas críticos.

---

## Testing Examples

### Smoke Test (TST/PRD)

```bash
#!/bin/bash
set -e

APP_URL="http://myapp.tst.asgard.internal"
# ou APP_URL="http://myapp.prd.asgard.internal"

# Health check
response=$(curl -s -o /dev/null -w "%{http_code}" $APP_URL/health)
if [ "$response" != "200" ]; then
  echo "❌ Health check failed: HTTP $response"
  exit 1
fi

echo "✅ Smoke test passed"
```

### Integration Test (PRD only)

```bash
#!/bin/bash
set -e

APP_URL="http://myapp.prd.asgard.internal"

# Test database connectivity
curl -f $APP_URL/api/db-health

# Test external API
curl -f $APP_URL/api/external-health

# Test critical endpoint
response=$(curl -s -X POST $APP_URL/api/critical-endpoint \
  -H "Content-Type: application/json" \
  -d '{"test": true}')

if [[ "$response" != *"success"* ]]; then
  echo "❌ Integration test failed"
  exit 1
fi

echo "✅ Integration tests passed"
```

---

## Rollback Procedures

### Rollback via Kubernetes

```bash
# TST
kubectl rollout undo deployment/myapp -n tst

# PRD (Blue-Green: switch back to blue)
kubectl patch service myapp -n prd \
  -p '{"spec":{"selector":{"version":"blue"}}}'
```

### Rollback via Harbor + Redeploy

```bash
# List previous tags
curl -u $HARBOR_USERNAME:$HARBOR_PASSWORD \
  "http://192.168.1.100:30880/api/v2.0/projects/prd/repositories/myapp/artifacts"

# Redeploy previous version
kubectl set image deployment/myapp \
  myapp=192.168.1.100:30880/prd/myapp:v1.0.0 \
  -n prd
```

---

## Best Practices

### CI Stage
- ✅ Run Semgrep before building (fail fast)
- ✅ Cache dependencies (npm, pip, go mod)
- ✅ Use multi-stage Docker builds
- ✅ Scan image before pushing to registry
- ✅ Tag images with semantic versioning

### CD Stage
- ✅ Use External Secrets Operator (não hardcode secrets)
- ✅ Set resource limits nos Deployments
- ✅ Configure readiness/liveness probes
- ✅ Use Blue-Green deploys em PRD
- ✅ Run smoke tests após deploy
- ✅ Manual approval para PRD

### Security
- ✅ Semgrep + Trivy em todos os pipelines
- ✅ Harbor blocking vulnerabilities em PRD
- ✅ Robot accounts com permissões mínimas
- ✅ Rotate credentials periodicamente
- ✅ Audit logs habilitados

### Observability
- ✅ Logs centralizados (Loki)
- ✅ Métricas coletadas (Prometheus)
- ✅ Dashboards configurados (Grafana)
- ✅ Alertas críticos (Alertmanager)
- ✅ Notificações (Slack/Email)

---

## Troubleshooting

### Pipeline falha no Semgrep

```bash
# Executar localmente para debug
semgrep --config=auto --verbose .

# Ver rules ativas
semgrep --show-supported-languages
semgrep --config=auto --dry-run .
```

### Pipeline falha no Trivy

```bash
# Executar localmente
trivy image --severity CRITICAL myapp:latest

# Ver vulnerabilidades detalhadas
trivy image --format json myapp:latest | jq .
```

### Harbor push bloqueado

```bash
# Ver scan results via API
curl -u admin:Harbor12345 \
  "http://192.168.1.100:30880/api/v2.0/projects/prd/repositories/myapp/artifacts/v1.0.0/additions/vulnerabilities"

# Temporariamente desabilitar blocking (não recomendado)
# Harbor UI → Projects → prd → Configuration → Prevent vulnerable images: OFF
```

### Deploy falha (K8s)

```bash
# Ver logs do pod
kubectl -n prd logs deployment/myapp

# Ver eventos
kubectl -n prd get events --sort-by='.lastTimestamp'

# Ver describe
kubectl -n prd describe pod <pod-name>
```

---

## Referências

- [STACK.md](../../docs/STACK.md) - Arquitetura completa
- [HARBOR.md](../../docs/HARBOR.md) - Container registry
- [VAULT.md](../../docs/VAULT.md) - Secrets management
- Semgrep: https://semgrep.dev/docs/
- Trivy: https://aquasecurity.github.io/trivy/
