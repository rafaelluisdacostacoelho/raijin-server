# Harbor Container Registry

Guia completo de instalação e uso do Harbor como registry privado de containers com vulnerability scanning integrado.

## Índice

- [Visão Geral](#visão-geral)
- [Instalação](#instalação)
- [Arquitetura](#arquitetura)
- [Projetos e Ambientes](#projetos-e-ambientes)
- [Uso Básico](#uso-básico)
- [Políticas de Retenção](#políticas-de-retenção)
- [Robot Accounts (CI/CD)](#robot-accounts-cicd)
- [Vulnerability Scanning](#vulnerability-scanning)
- [Integração com Kubernetes](#integração-com-kubernetes)
- [Integração com CI/CD](#integração-com-cicd)
- [Backup e Restore](#backup-e-restore)
- [Troubleshooting](#troubleshooting)

---

## Visão Geral

**Harbor** é um registry open source para containers OCI/Docker com recursos enterprise:

### Recursos Principais

- ✅ **Vulnerability Scanning**: Trivy integrado para scan automático
- ✅ **Retention Policies**: Garbage collection automático de imagens antigas
- ✅ **RBAC**: Controle de acesso granular por projeto
- ✅ **Robot Accounts**: Credenciais dedicadas para CI/CD
- ✅ **Replication**: Sincronização entre registries
- ✅ **Webhooks**: Notificações para eventos (push, pull, scan)
- ✅ **Helm Chart Repository**: Armazena charts além de images
- ✅ **Content Trust**: Assinatura de imagens (Cosign/Notary)
- ✅ **Audit Logs**: Rastreamento completo de operações

### Componentes

```
Harbor Stack:
├── Portal (UI)
├── Core (API)
├── Registry (Docker Registry v2)
├── Trivy (Vulnerability Scanner)
├── ChartMuseum (Helm Charts)
├── JobService (Background jobs)
├── PostgreSQL (Metadados)
├── Redis (Cache)
└── MinIO (Storage backend para images)
```

---

## Instalação

### Pré-requisitos

- Kubernetes cluster funcionando
- MinIO instalado e acessível
- ~2-3GB RAM disponível
- Acesso via VPN (para UI)

### Instalação via raijin-server

```bash
raijin-server install harbor
```

**Prompts**:
- `Namespace para Harbor`: `harbor` (padrão)
- `MinIO host`: `minio.minio.svc:9000` (interno) ou `192.168.1.81:30900` (NodePort)
- `MinIO Access Key`: `harbor-user` (criado automaticamente com least-privilege)
- `MinIO Secret Key`: (gerado automaticamente)
- `NodePort para Harbor UI/Registry`: `30880` (padrão)
- `Senha do admin`: `Harbor12345` (troque!)

### O que é instalado

1. **Harbor** (todos componentes)
   - Chart: `harbor/harbor`
   - Namespace: `harbor`
   - Storage: MinIO S3-compatible
   - UI/Registry: NodePort 30880

2. **Buckets MinIO criados**:
   - `harbor-registry` (images)
   - `harbor-chartmuseum` (helm charts)
   - `harbor-jobservice` (job logs)

3. **Projetos criados automaticamente**:
   - `tst` (test/staging)
   - `prd` (production)

4. **MinIO Least-Privilege**:
   - Usuário `harbor-user` criado com acesso **apenas** aos buckets:
     - `harbor-registry`
     - `harbor-chartmuseum`
     - `harbor-jobservice`
   - Credenciais salvas em secret `minio-harbor-credentials` no namespace harbor

---

## Arquitetura

### Fluxo de Push/Pull

```
┌──────────────────────────────────────────────────────────────┐
│                   Developer Workstation                      │
│                                                              │
│  docker build -t myapp:v1.0.0 .                             │
│  docker tag myapp:v1.0.0 harbor.asgard:30880/tst/myapp:v1  │
│  docker push harbor.asgard:30880/tst/myapp:v1               │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTPS/HTTP
                     ▼
        ┌────────────────────────┐
        │   Harbor Core (API)    │
        │   - Autenticação       │
        │   - RBAC Check         │
        │   - Trigger Scan       │
        └───────┬────────────────┘
                │
                ├──────────────────┐
                │                  │
                ▼                  ▼
    ┌───────────────────┐  ┌──────────────┐
    │  Docker Registry  │  │    Trivy     │
    │  (image layers)   │  │  (scanner)   │
    └─────┬─────────────┘  └──────┬───────┘
          │                       │
          │ Store blobs           │ Scan result
          ▼                       ▼
    ┌─────────────────────────────────┐
    │         MinIO S3                │
    │   (harbor-registry bucket)      │
    └─────────────────────────────────┘
          ▲
          │ Metadata
          │
    ┌─────┴──────────┐
    │  PostgreSQL    │
    │  (projects,    │
    │   artifacts)   │
    └────────────────┘
```

### Padrão TST vs PRD

| Aspecto | TST (Test/Staging) | PRD (Production) |
|---------|-------------------|------------------|
| **Branch Source** | `develop` | `main`/`master` |
| **Auto-scan** | ✅ Sim | ✅ Sim |
| **Block Vulnerabilities** | ❌ Não | ✅ Critical+ |
| **Content Trust** | ❌ Opcional | ✅ Recomendado |
| **Retention** | 10 images / 30 dias | 20 images / 90 dias |
| **Robot Permissions** | Push, Pull, Delete | Push, Pull |
| **Immutability** | ❌ Tags mutáveis | ✅ Tags imutáveis |

---

## Projetos e Ambientes

### Projeto TST (Test/Staging)

**Finalidade**: Testes, staging, QA

**Configuração**:
```yaml
Project: tst
Public: No (privado)
Auto-scan: Yes
Prevent vulnerable images: No
Content trust: No
Severity threshold: Low (scan tudo)
```

**Workflow**:
```bash
# CI/CD pipeline para develop branch
git push origin develop
  ↓
[CI Build]
  ↓
docker tag myapp:dev harbor.asgard:30880/tst/myapp:develop-${BUILD_ID}
docker push harbor.asgard:30880/tst/myapp:develop-${BUILD_ID}
  ↓
[Auto-scan Trivy]
  ↓
[Deploy to K8s TST namespace]
```

### Projeto PRD (Production)

**Finalidade**: Produção, releases estáveis

**Configuração**:
```yaml
Project: prd
Public: No (privado)
Auto-scan: Yes
Prevent vulnerable images: Yes (CRITICAL)
Content trust: Yes (assinatura obrigatória)
Severity threshold: Critical
```

**Workflow**:
```bash
# CI/CD pipeline para main/master branch
git push origin main
  ↓
[CI Build + Tests]
  ↓
docker tag myapp:v1.0.0 harbor.asgard:30880/prd/myapp:v1.0.0
docker push harbor.asgard:30880/prd/myapp:v1.0.0
  ↓
[Auto-scan Trivy]
  ↓
[Check: Se CRITICAL vulnerabilities → BLOCK]
  ↓
[Sign image with Cosign]
  ↓
[Deploy to K8s PRD namespace]
```

---

## Uso Básico

### Acesso à UI

```
URL: http://192.168.1.81:30880
Usuário: admin
Senha: Harbor12345 (ou a que você configurou)
```

### Docker Login

```bash
# Via VPN
docker login 192.168.1.81:30880
Username: admin
Password: Harbor12345

# Ou via domínio interno (se DNS configurado)
docker login harbor.asgard.internal:30880
```

### Push de Imagem

```bash
# 1. Build local
docker build -t myapp:v1.0.0 .

# 2. Tag para Harbor (TST)
docker tag myapp:v1.0.0 192.168.1.81:30880/tst/myapp:v1.0.0

# 3. Push
docker push 192.168.1.81:30880/tst/myapp:v1.0.0

# 4. Tag para Harbor (PRD)
docker tag myapp:v1.0.0 192.168.1.81:30880/prd/myapp:v1.0.0
docker push 192.168.1.81:30880/prd/myapp:v1.0.0
```

### Pull de Imagem

```bash
docker pull 192.168.1.81:30880/tst/myapp:v1.0.0
docker pull 192.168.1.81:30880/prd/myapp:v1.0.0
```

### Listar Imagens

```bash
# Via CLI (usando curl)
curl -u admin:Harbor12345 \
  http://192.168.1.81:30880/api/v2.0/projects/tst/repositories

# Via UI
Harbor → Projects → tst → Repositories
```

---

## Políticas de Retenção

### TST: Manter últimas 10 imagens OU 30 dias

**Configuração via UI**:
1. Harbor → Projects → tst → Policy → Tag Retention
2. Add Rule:
   - **Rule 1**: Retain the most recently pushed # images: `10`
   - **Rule 2**: Retain the images pushed within the last # days: `30`
   - **Scope**: All repositories
   - **Tag**: All tags (`**`)
3. Schedule: Daily at 00:00 (cron: `0 0 * * *`)

**Exemplo**:
```
Repositório: tst/myapp
Imagens:
├── v1.0.0 (pushed 45 dias atrás) → DELETADA (> 30 dias)
├── v1.0.1 (pushed 25 dias atrás) → MANTIDA
├── v1.0.2 (pushed 20 dias atrás) → MANTIDA
├── ...
└── v1.0.15 (pushed hoje) → MANTIDA

Resultado: Mantém as 10 mais recentes OU tudo dentro de 30 dias
```

### PRD: Manter últimas 20 imagens OU 90 dias

**Configuração via UI**:
1. Harbor → Projects → prd → Policy → Tag Retention
2. Add Rule:
   - **Rule 1**: Retain the most recently pushed # images: `20`
   - **Rule 2**: Retain the images pushed within the last # days: `90`
   - **Scope**: All repositories
   - **Tag**: All tags (`**`)
3. Schedule: Weekly on Sunday at 02:00 (cron: `0 2 * * 0`)

### Garbage Collection

**Configuração global**:
1. Harbor → Administration → Garbage Collection
2. Schedule: Daily at 03:00 (cron: `0 3 * * *`)
3. Options:
   - ✅ Delete untagged artifacts
   - ✅ Delete manifest immediately
   - ⚠️ Dry run (para testar antes)

**O que faz**:
- Remove blobs órfãos (layers não referenciados)
- Libera espaço no MinIO
- Roda após retention policies

---

## Robot Accounts (CI/CD)

### Por que usar Robot Accounts?

- ✅ Credenciais dedicadas (não compartilha admin)
- ✅ Permissões granulares (apenas o necessário)
- ✅ Rotação fácil (revoga e cria novo)
- ✅ Audit trail (rastreia operações do bot)

### Criar Robot Account (TST)

**Via UI**:
1. Harbor → Projects → tst
2. Robot Accounts → New Robot Account
3. Configurar:
   - **Name**: `cicd-tst`
   - **Description**: "CI/CD pipeline for TST environment"
   - **Expiration**: 365 days (ou Never)
   - **Permissions**:
     - ✅ Push artifact
     - ✅ Pull artifact
     - ✅ Delete artifact
     - ✅ Read Helm chart
     - ✅ Create Helm chart version
4. Create → **COPIAR TOKEN GERADO** (não será mostrado novamente!)

**Resultado**:
```
Robot Name: robot$cicd-tst
Token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Armazenar Token no Vault

```bash
kubectl -n vault exec vault-0 -- \
  env VAULT_TOKEN=<root-token> \
  vault kv put secret/harbor/robot-tst \
    username=robot$cicd-tst \
    token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Usar Robot Account no CI/CD

```bash
# No pipeline (GitHub Actions, GitLab CI, Harness, etc)
- name: Login to Harbor
  run: |
    echo ${{ secrets.HARBOR_ROBOT_TOKEN }} | \
      docker login 192.168.1.81:30880 \
      -u robot$cicd-tst --password-stdin

- name: Push image
  run: |
    docker push 192.168.1.81:30880/tst/myapp:${{ github.sha }}
```

---

## Vulnerability Scanning

### Trivy Integrado

Harbor usa **Trivy** para scan de vulnerabilidades:

- **CVSS Scores**: Critical, High, Medium, Low
- **Databases**: CVE, NVD, OSV, etc
- **Layers**: Analisa cada layer da imagem
- **Dependencies**: Detecta vulnerabilidades em pacotes

### Auto-scan

**Configurado em ambos projetos** (tst e prd):
- Trigger: Ao fazer push da imagem
- Async: Não bloqueia push (scan em background)
- Resultado: Visível na UI após ~30s-2min

### Visualizar Scan Results

**Via UI**:
1. Harbor → Projects → tst/prd → Repositories
2. Clicar na imagem → Tags
3. Ver coluna "Vulnerabilities": `0 Critical, 5 High, 20 Medium...`
4. Clicar no número → Detalhes do scan

**Via API**:
```bash
curl -u admin:Harbor12345 \
  "http://192.168.1.81:30880/api/v2.0/projects/prd/repositories/myapp/artifacts/v1.0.0/additions/vulnerabilities"
```

### Prevent Vulnerable Images (PRD)

**Em produção**, Harbor bloqueia push de imagens com vulnerabilidades críticas:

```bash
docker push 192.168.1.81:30880/prd/myapp:vulnerable

# Erro:
# unknown: current image with 3 critical vulnerabilities cannot be pushed 
# due to configured policy in 'Prevent images with vulnerability' project setting
```

**Solução**: Corrigir vulnerabilidades antes do push.

### Whitelist CVEs

Se uma vulnerabilidade for falso positivo:
1. Harbor → Projects → prd → Configuration
2. CVE Allowlist → Add
3. CVE-ID: `CVE-2024-12345`
4. Reason: "False positive - not exploitable in our context"

---

## Integração com Kubernetes

### Criar imagePullSecret

```bash
# Método 1: Via kubectl
kubectl create secret docker-registry harbor-secret \
  --docker-server=192.168.1.81:30880 \
  --docker-username=admin \
  --docker-password=Harbor12345 \
  --namespace=default

# Método 2: Via robot account (recomendado)
kubectl create secret docker-registry harbor-robot \
  --docker-server=192.168.1.81:30880 \
  --docker-username=robot$cicd-prd \
  --docker-password=<ROBOT_TOKEN> \
  --namespace=production
```

### Usar em Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: production
spec:
  template:
    spec:
      imagePullSecrets:
      - name: harbor-robot
      
      containers:
      - name: myapp
        image: 192.168.1.81:30880/prd/myapp:v1.0.0
        ports:
        - containerPort: 8080
```

### ServiceAccount Default

Para não repetir `imagePullSecrets` em todo Deployment:

```bash
# Patch no ServiceAccount default
kubectl patch serviceaccount default -n production \
  -p '{"imagePullSecrets": [{"name": "harbor-robot"}]}'
```

Agora todos os pods no namespace `production` usarão automaticamente.

---

## Integração com CI/CD

### Fluxo Completo (GitHub Actions + Harbor + K8s)

```yaml
# .github/workflows/deploy-tst.yml
name: Deploy to TST
on:
  push:
    branches: [develop]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to Harbor
        run: |
          echo ${{ secrets.HARBOR_ROBOT_TST_TOKEN }} | \
            docker login 192.168.1.81:30880 \
            -u robot$cicd-tst --password-stdin
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: |
            192.168.1.81:30880/tst/myapp:${{ github.sha }}
            192.168.1.81:30880/tst/myapp:develop
      
      - name: Wait for scan
        run: sleep 60  # Aguarda Trivy scan
      
      - name: Check vulnerabilities
        run: |
          VULNS=$(curl -s -u admin:${{ secrets.HARBOR_ADMIN_PASSWORD }} \
            "http://192.168.1.81:30880/api/v2.0/projects/tst/repositories/myapp/artifacts/${{ github.sha }}/additions/vulnerabilities" \
            | jq '.summary.critical')
          
          if [ "$VULNS" -gt 0 ]; then
            echo "⚠️  Warning: $VULNS critical vulnerabilities found"
          fi
      
      - name: Deploy to K8s TST
        run: |
          kubectl set image deployment/myapp \
            myapp=192.168.1.81:30880/tst/myapp:${{ github.sha }} \
            -n tst
```

### Harness Pipeline (exemplo)

```yaml
pipeline:
  name: Deploy myapp to PRD
  stages:
    - stage:
        name: Build
        type: CI
        spec:
          steps:
            - step:
                type: BuildAndPushDockerRegistry
                name: Build and Push to Harbor
                spec:
                  connectorRef: harbor_prd
                  repo: 192.168.1.81:30880/prd/myapp
                  tags:
                    - <+pipeline.sequenceId>
                    - latest
    
    - stage:
        name: Security Scan
        type: SecurityTests
        spec:
          steps:
            - step:
                type: AquaTrivy
                name: Trivy Scan
                spec:
                  mode: orchestration
                  config: default
                  target:
                    type: container
                    name: 192.168.1.81:30880/prd/myapp
                    tag: <+pipeline.sequenceId>
                  advanced:
                    args:
                      severity: CRITICAL,HIGH
                      exit-code: 1
    
    - stage:
        name: Deploy to PRD
        type: Deployment
        spec:
          service:
            serviceRef: myapp-prd
          environment:
            environmentRef: production
          execution:
            steps:
              - step:
                  type: K8sRollingDeploy
                  name: Rolling Deploy
                  spec:
                    skipDryRun: false
```

---

## Backup e Restore

### O que fazer backup

1. **Metadados (PostgreSQL)**
   - Projetos, usuários, políticas
   - Scan results, audit logs

2. **Images (MinIO)**
   - Buckets: `harbor-registry`, `harbor-chartmuseum`, `harbor-jobservice`
   - Já coberto pelo backup do MinIO (Velero)

### Backup PostgreSQL

```bash
# Dentro do pod do Harbor database
kubectl -n harbor exec -it harbor-database-0 -- \
  pg_dump -U postgres registry > /tmp/harbor-db-backup.sql

# Copiar para local
kubectl -n harbor cp harbor-database-0:/tmp/harbor-db-backup.sql \
  ./harbor-db-backup-$(date +%Y%m%d).sql
```

### Restore PostgreSQL

```bash
# Upload backup
kubectl -n harbor cp harbor-db-backup-20260202.sql \
  harbor-database-0:/tmp/harbor-restore.sql

# Restore
kubectl -n harbor exec -it harbor-database-0 -- \
  psql -U postgres registry < /tmp/harbor-restore.sql
```

### Backup MinIO (via Velero)

```bash
# Velero já faz backup diário do bucket harbor-registry
velero backup get | grep harbor

# Restore específico
velero restore create --from-backup daily-backup-20260202
```

---

## Troubleshooting

### Harbor UI não acessível

```bash
# Verificar pods
kubectl -n harbor get pods
# Todos devem estar Running/Ready

# Verificar service NodePort
kubectl -n harbor get svc harbor
# Deve mostrar NodePort 30880

# Testar acesso local
curl http://192.168.1.81:30880
```

### Push blocked: "unauthorized"

```bash
# Verificar login
docker login 192.168.1.81:30880
# Inserir credenciais corretas

# Verificar permissões do robot account
Harbor UI → Projects → tst → Robot Accounts → cicd-tst
# Confirmar permissões: Push artifact
```

### Push blocked: "vulnerable image"

```bash
# Ver scan results
Harbor UI → Projects → prd → Repositories → myapp → Vulnerabilities

# Temporariamente desabilitar (não recomendado em PRD)
Harbor UI → Projects → prd → Configuration
→ Prevent vulnerable images from running: OFF

# Solução correta: corrigir vulnerabilidades
docker build --no-cache -t myapp:fixed .
```

### Trivy scan falhou

```bash
# Ver logs do Trivy
kubectl -n harbor logs deployment/harbor-trivy

# Atualizar database do Trivy
kubectl -n harbor exec -it deployment/harbor-trivy -- trivy image --download-db-only

# Retry scan via UI
Harbor UI → Repositories → myapp → Tags → [Scan]
```

### Storage cheio (MinIO)

```bash
# Ver uso do bucket
mc du minio/harbor-registry

# Trigger garbage collection manual
Harbor UI → Administration → Garbage Collection → [Run Now]

# Verificar retention policies
Harbor UI → Projects → tst → Policy → Tag Retention → [Run Now]
```

### "Digest mismatch" ao fazer pull

```bash
# Problema: Image corrupta ou modificada

# Solução: Re-push da imagem
docker push --force 192.168.1.81:30880/tst/myapp:v1.0.0

# Ou deletar e fazer push novo
# Via UI: Harbor → Repositories → myapp → Tags → [Delete]
```

---

## Comandos Úteis

```bash
# Status geral
kubectl -n harbor get pods
kubectl -n harbor get svc
kubectl -n harbor top pods

# Logs
kubectl -n harbor logs -f deployment/harbor-core
kubectl -n harbor logs -f deployment/harbor-registry
kubectl -n harbor logs -f deployment/harbor-trivy

# Acesso ao DB
kubectl -n harbor exec -it harbor-database-0 -- psql -U postgres registry

# Restart components
kubectl -n harbor rollout restart deployment/harbor-core
kubectl -n harbor rollout restart deployment/harbor-registry

# Ver buckets MinIO
mc ls minio/harbor-registry/
mc du minio/harbor-registry/

# API calls
curl -u admin:Harbor12345 http://192.168.1.81:30880/api/v2.0/systeminfo
curl -u admin:Harbor12345 http://192.168.1.81:30880/api/v2.0/projects
```

---

## Checklist de Produção

- [ ] Trocar senha do admin (não usar `Harbor12345`)
- [ ] Criar robot accounts para CI/CD (tst e prd)
- [ ] Armazenar tokens no Vault
- [ ] Configurar retention policies (tst: 10/30d, prd: 20/90d)
- [ ] Configurar garbage collection (diário às 3h)
- [ ] Habilitar "Prevent vulnerable images" em PRD
- [ ] Configurar webhooks para notificar CI/CD
- [ ] Testar push/pull de imagens
- [ ] Testar vulnerability scan
- [ ] Criar imagePullSecrets no K8s
- [ ] Documentar fluxo de deploy para a equipe
- [ ] Backup do PostgreSQL (semanal)
- [ ] Monitorar uso de storage (MinIO)
- [ ] Configurar alertas (se harbor consumir > 80% RAM)
- [ ] Testar restore de backup

---

**Instalado via**: `raijin-server install harbor` (módulo harbor.py)

**Documentação oficial**: https://goharbor.io/docs/
