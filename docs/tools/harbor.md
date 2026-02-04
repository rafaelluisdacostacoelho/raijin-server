# Harbor Container Registry

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Velero](velero.md) | [Próximo: MinIO →](minio.md)

---

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
- [Glossário](#glossário)
- [Boas e Más Práticas](#boas-e-más-práticas)

---

## Visão Geral

**Harbor¹** é um **registry² open source** para containers **OCI²**/Docker com recursos enterprise:

### Recursos Principais

- ✅ **Vulnerability Scanning³**: **Trivy⁴** integrado para scan automático
- ✅ **Retention Policies**: Garbage collection automático de imagens antigas
- ✅ **RBAC⁵**: Controle de acesso granular por projeto
- ✅ **Robot Accounts⁶**: Credenciais dedicadas para CI/CD
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
- `MinIO host`: `minio.minio.svc:9000` (interno) ou `192.168.1.100:30900` (NodePort)
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
URL: http://192.168.1.100:30880
Usuário: admin
Senha: Harbor12345 (ou a que você configurou)
```

### Docker Login

```bash
# Via VPN
docker login 192.168.1.100:30880
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
docker tag myapp:v1.0.0 192.168.1.100:30880/tst/myapp:v1.0.0

# 3. Push
docker push 192.168.1.100:30880/tst/myapp:v1.0.0

# 4. Tag para Harbor (PRD)
docker tag myapp:v1.0.0 192.168.1.100:30880/prd/myapp:v1.0.0
docker push 192.168.1.100:30880/prd/myapp:v1.0.0
```

### Pull de Imagem

```bash
docker pull 192.168.1.100:30880/tst/myapp:v1.0.0
docker pull 192.168.1.100:30880/prd/myapp:v1.0.0
```

### Listar Imagens

```bash
# Via CLI (usando curl)
curl -u admin:Harbor12345 \
  http://192.168.1.100:30880/api/v2.0/projects/tst/repositories

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
      docker login 192.168.1.100:30880 \
      -u robot$cicd-tst --password-stdin

- name: Push image
  run: |
    docker push 192.168.1.100:30880/tst/myapp:${{ github.sha }}
```

---

## Glossário

1. **Registry**: Serviço que armazena e distribui imagens de containers (Docker/OCI).
2. **OCI** (Open Container Initiative): Padrão aberto para formato de imagens de containers.
3. **Vulnerability Scanning**: Análise automática de imagens para detectar CVEs (Common Vulnerabilities and Exposures).
4. **Trivy**: Scanner de vulnerabilidades open-source da Aqua Security integrado ao Harbor.
5. **RBAC** (Role-Based Access Control): Controle de acesso baseado em roles (Project Admin, Developer, Guest).
6. **Robot Account**: Credencial não-humana com permissões específicas para automação (CI/CD).
7. **Artifact**: Termo genérico do Harbor para imagens, Helm charts e outros artefatos armazenados.
8. **Tag**: Identificador de versão de uma imagem (ex.: `v1.0.0`, `latest`).
9. **Layer**: Camada filesystem de uma imagem OCI (cada instrução Dockerfile gera layer).
10. **Blob**: Unidade de armazenamento de layers no backend S3.
11. **Retention Policy**: Regra automática para deletar imagens antigas (por idade ou quantidade).
12. **Garbage Collection**: Processo que remove blobs órfãos liberando storage.
13. **Immutable Tag**: Tag que não pode ser sobrescrita (boa prática para PRD).
14. **Content Trust**: Verificação de assinatura digital de imagens (Cosign/Notary).
15. **CVE** (Common Vulnerabilities and Exposures): Base de dados pública de vulnerabilidades conhecidas.

---

## Boas práticas ✅

1. **Projetos separados por ambiente**: TST e PRD com políticas distintas.
2. **Robot accounts por pipeline**: Credenciais dedicadas para cada CI/CD.
3. **Immutable tags em PRD**: Prevenir sobrescrita acidental de versões.
4. **Vulnerability blocking**: Bloquear push/pull de imagens com CVEs críticos em PRD.
5. **Retention policies ativas**: Evitar crescimento ilimitado do storage.
6. **Garbage collection agendado**: Rodar diariamente para liberar espaço.
7. **Scan automático habilitado**: Escanear todas as imagens no push.
8. **Tags semânticas**: Usar versionamento semântico (v1.2.3) ao invés de `latest` em PRD.
9. **Backup de metadados**: PostgreSQL do Harbor contém configurações críticas.
10. **Least-privilege MinIO user**: Usuário dedicado apenas aos buckets do Harbor.
11. **Audit logs habilitados**: Rastrear todas as operações para compliance.
12. **Webhooks para alertas**: Notificar quando vulnerabilidades críticas forem detectadas.
13. **Limitar acesso público**: Manter projetos privados; expor apenas via VPN.
14. **Rotação de robot accounts**: Renovar tokens periodicamente (ex.: a cada 6 meses).
15. **Content trust em PRD**: Assinar imagens com Cosign para garantir proveniência.

---

## Práticas ruins ❌

1. **Usar conta admin em CI/CD**: Expõe credenciais privilegiadas.
2. **Tags mutáveis em PRD**: Permite sobrescrita acidental de `v1.0.0`.
3. **Sem retention policies**: Storage cresce indefinidamente.
4. **Sem garbage collection**: Blobs órfãos consomem espaço.
5. **Ignorar scans**: Deployar imagens sem verificar vulnerabilidades.
6. **Tag `latest` em produção**: Dificulta rollback e troubleshooting.
7. **Projetos públicos sem necessidade**: Expõe imagens desnecessariamente.
8. **Credenciais hardcoded**: Armazenar tokens em código ou CI/CD visível.
9. **Não bloquear CVEs críticos**: Permitir deploy de imagens vulneráveis.
10. **Misturar ambientes no mesmo projeto**: TST e PRD no mesmo namespace do Harbor.
11. **Sem backup de PostgreSQL**: Perder configurações e metadados.
12. **Robot accounts sem expiração**: Tokens permanentes aumentam risco.
13. **Não testar restores**: Backups sem validação podem estar corrompidos.
14. **Logs não monitorados**: Perder tentativas de acesso não autorizado.
15. **Storage compartilhado**: Não usar least-privilege no MinIO.

---

## Diagnóstico avançado

### Verificar health do Harbor

```bash
kubectl get pods -n harbor
kubectl logs -n harbor -l app=harbor-core --tail=100 -f
```

### Ver uso de storage no MinIO

```bash
mc du minio/harbor-registry/
mc ls -r minio/harbor-registry/ | head -20
```

### Listar imagens via API

```bash
curl -u admin:Harbor12345 \
  http://192.168.1.100:30880/api/v2.0/projects/prd/repositories | jq
```

### Ver CVEs de uma imagem específica

```bash
curl -u admin:Harbor12345 \
  "http://192.168.1.100:30880/api/v2.0/projects/prd/repositories/myapp/artifacts/v1.0.0/additions/vulnerabilities" | jq
```

### Forçar scan manual

```bash
curl -X POST -u admin:Harbor12345 \
  "http://192.168.1.100:30880/api/v2.0/projects/prd/repositories/myapp/artifacts/v1.0.0/scan"
```

### Verificar retention policy execution

```bash
kubectl logs -n harbor -l app=harbor-jobservice | grep retention
```

### Garbage collection manual

```bash
# Via UI: Administration → Garbage Collection → Run Now
# Ou via API:
curl -X POST -u admin:Harbor12345 \
  "http://192.168.1.100:30880/api/v2.0/system/gc/schedule"
```

### Ver audit logs

```bash
kubectl logs -n harbor -l app=harbor-core | grep audit
# Ou via UI: Administration → Audit Logs
```

### Verificar conectividade com MinIO

```bash
kubectl exec -n harbor deployment/harbor-registry -- nslookup minio.minio.svc
kubectl exec -n harbor deployment/harbor-registry -- wget -O- http://minio.minio.svc:9000/minio/health/ready
```

### Listar robot accounts ativos

```bash
curl -u admin:Harbor12345 \
  "http://192.168.1.100:30880/api/v2.0/projects/tst/robots" | jq
```

### Testar push/pull com robot account

```bash
echo $ROBOT_TOKEN | docker login 192.168.1.100:30880 -u robot$cicd-tst --password-stdin
docker pull 192.168.1.100:30880/tst/myapp:test
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Velero](velero.md)** | **[Próximo: MinIO →](minio.md)**
