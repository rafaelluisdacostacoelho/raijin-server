# Stack Completa de Infraestrutura e CI/CD

Documentação completa da stack de infraestrutura, observabilidade, segurança e CI/CD baseada em ferramentas 100% open source.

## Índice

- [Visão Geral](#visão-geral)
- [Arquitetura Completa](#arquitetura-completa)
- [Componentes por Camada](#componentes-por-camada)
- [Fluxos de Deploy](#fluxos-de-deploy)
- [Security Scanning](#security-scanning)
- [Padrões TST vs PRD](#padrões-tst-vs-prd)
- [Integração entre Componentes](#integração-entre-componentes)
- [Guias de Implementação](#guias-de-implementação)

---

## Visão Geral

### Stack Tecnológica

```
┌─────────────────────────────────────────────────────────────┐
│                  DEVELOPER WORKSTATION                      │
│  • Git Push (develop/main)                                  │
│  • VPN Access (10.8.0.2)                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   CI/CD PIPELINE (Harness)                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  CI Stage                                           │    │
│  │  1. Checkout code                                   │    │
│  │  2. Semgrep SAST scan                              │    │
│  │  3. Unit tests                                      │    │
│  │  4. Docker build                                    │    │
│  │  5. Trivy vulnerability scan                        │    │
│  │  6. Push to Harbor (tst/prd)                       │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  CD Stage                                           │    │
│  │  1. Get secrets from Vault                         │    │
│  │  2. Deploy to K8s (rolling update)                 │    │
│  │  3. Smoke tests                                     │    │
│  │  4. Notify (Slack/Email)                           │    │
│  └────────────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│               KUBERNETES CLUSTER (10.8.0.1)                 │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Infrastructure                                    │    │
│  │  • Calico CNI                                      │    │
│  │  • MetalLB LoadBalancer                           │    │
│  │  • Traefik Ingress                                │    │
│  │  • Cert-Manager                                    │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Storage & Backup                                  │    │
│  │  • MinIO (S3-compatible)                          │    │
│  │  • Velero (K8s backup)                            │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Secrets Management                                │    │
│  │  • Vault (centralized secrets)                    │    │
│  │  • External Secrets Operator                       │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Container Registry                                │    │
│  │  • Harbor (private registry)                      │    │
│  │  • Trivy (vulnerability scanner)                  │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Observability                                     │    │
│  │  • Prometheus (metrics)                           │    │
│  │  • Grafana (dashboards)                           │    │
│  │  • Loki (logs)                                    │    │
│  │  • Alertmanager (alerting)                        │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │  Application Workloads                             │    │
│  │  • TST Namespace (staging)                        │    │
│  │  • PRD Namespace (production)                     │    │
│  └───────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Princípios da Stack

1. **100% Open Source**: Sem dependências de software proprietário
2. **Security by Default**: Scanning, secrets management, network policies
3. **GitOps Ready**: Declarativo, versionado, auditável
4. **Production Grade**: HA, backup, monitoring, alerting
5. **Developer Friendly**: Self-service, rápido feedback

---

## Arquitetura Completa

### Diagrama de Integração

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            DEVELOPER FLOW                                │
└────────────┬────────────────────────────────────────────────────────────┘
             │
             │ git push origin develop/main
             ▼
┌────────────────────────┐
│   GitHub/GitLab        │
│   (Source Control)     │
└───────┬────────────────┘
        │ Webhook
        ▼
┌────────────────────────────────────────────────────────────────┐
│                    HARNESS CI PIPELINE                         │
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │  Code Quality    │  │  Security Scan   │                  │
│  │                  │  │                  │                  │
│  │  • Semgrep       │  │  • Trivy (code)  │                  │
│  │    SAST scan     │  │  • Trivy (deps)  │                  │
│  │  • Unit tests    │  │  • OWASP checks  │                  │
│  │  • Linters       │  │                  │                  │
│  └────────┬─────────┘  └────────┬─────────┘                  │
│           │                     │                             │
│           └──────────┬──────────┘                             │
│                      ▼                                         │
│           ┌─────────────────────┐                             │
│           │   Docker Build      │                             │
│           │   • Multi-stage     │                             │
│           │   • Layer caching   │                             │
│           └──────────┬──────────┘                             │
│                      │                                         │
│                      ▼                                         │
│           ┌─────────────────────┐                             │
│           │  Container Scan     │                             │
│           │  • Trivy image      │                             │
│           │  • Check threshold  │                             │
│           └──────────┬──────────┘                             │
│                      │                                         │
│                      ▼                                         │
│           ┌─────────────────────┐                             │
│           │  Push to Harbor     │◄────────────────┐           │
│           │  • tst/ or prd/     │                 │           │
│           │  • Auto-scan Trivy  │                 │           │
│           └──────────┬──────────┘                 │           │
└───────────────────────┼────────────────────────────┼───────────┘
                        │                            │
                        │ Trigger CD                 │
                        ▼                            │
┌────────────────────────────────────────────────────┼───────────┐
│                    HARNESS CD PIPELINE             │           │
│                                                    │           │
│  ┌──────────────────────────────────────────┐    │           │
│  │  1. Get image from Harbor                 │────┘           │
│  │     • Verify scan status                  │                │
│  │     • Check retention policy              │                │
│  └────────────────┬──────────────────────────┘                │
│                   │                                            │
│                   ▼                                            │
│  ┌──────────────────────────────────────────┐                │
│  │  2. Get secrets from Vault               │◄──────┐        │
│  │     • External Secrets Operator          │       │        │
│  │     • Sync to K8s Secrets                │       │        │
│  └────────────────┬──────────────────────────┘       │        │
│                   │                                   │        │
│                   ▼                                   │        │
│  ┌──────────────────────────────────────────┐       │        │
│  │  3. Deploy to Kubernetes                 │       │        │
│  │     • Rolling update                     │       │        │
│  │     • Health checks                      │       │        │
│  │     • Readiness probes                   │       │        │
│  └────────────────┬──────────────────────────┘       │        │
│                   │                                   │        │
│                   ▼                                   │        │
│  ┌──────────────────────────────────────────┐       │        │
│  │  4. Post-deploy validation               │       │        │
│  │     • Smoke tests                        │       │        │
│  │     • Integration tests                  │       │        │
│  └──────────────────────────────────────────┘       │        │
└────────────────────────────────────────────────────────────────┘
                   │                                   │
                   ▼                                   │
┌─────────────────────────────────────────────────────┼────────┐
│                  KUBERNETES CLUSTER                 │        │
│                                                     │        │
│  ┌────────────────────┐  ┌───────────────────┐    │        │
│  │  TST Namespace     │  │  PRD Namespace    │    │        │
│  │  • Staging apps    │  │  • Prod apps      │    │        │
│  │  • Test data       │  │  • Real data      │    │        │
│  └────────────────────┘  └───────────────────┘    │        │
│                                                     │        │
│  ┌───────────────────────────────────────────┐    │        │
│  │  Secrets (from Vault via ESO)             │◄───┘        │
│  │  • DB credentials                         │             │
│  │  • API keys                               │             │
│  │  • TLS certificates                       │             │
│  └───────────────────────────────────────────┘             │
│                                                             │
│  ┌───────────────────────────────────────────┐             │
│  │  Images (from Harbor)                     │◄────────────┤
│  │  • harbor.asgard:30880/tst/myapp         │             │
│  │  • harbor.asgard:30880/prd/myapp         │             │
│  └───────────────────────────────────────────┘             │
│                                                             │
│  ┌───────────────────────────────────────────┐             │
│  │  Observability                            │             │
│  │  • Prometheus (metrics scraping)          │             │
│  │  • Loki (log aggregation)                │             │
│  │  • Grafana (dashboards)                  │             │
│  └───────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

---

## Componentes por Camada

### 1. Infrastructure Layer

| Componente | Versão | Finalidade | Status | NodePort |
|------------|--------|------------|--------|----------|
| **Kubernetes** | 1.31+ | Orchestração de containers | ✅ Instalado | - |
| **Calico** | 3.28+ | CNI + Network Policies | ✅ Instalado | - |
| **MetalLB** | 0.14+ | LoadBalancer bare-metal | ✅ Instalado | - |
| **Traefik** | 3.0+ | Ingress Controller | ✅ Instalado | 30080/30443 |
| **Cert-Manager** | 1.14+ | TLS/SSL automation | ✅ Instalado | - |

**Documentação**: Ver módulos `kubernetes`, `calico`, `metallb`, `traefik`, `cert_manager`

---

### 2. Storage & Backup Layer

| Componente | Versão | Finalidade | Status | NodePort |
|------------|--------|------------|--------|----------|
| **MinIO** | RELEASE.2024+ | S3-compatible storage | ✅ Instalado | 30900/30901 |
| **Velero** | 1.13+ | K8s backup/restore | ✅ Instalado | - |

**Buckets MinIO**:
- `vault-storage`: Vault backend persistence
- `velero-backups`: Cluster backups (daily at 02:00 UTC)
- `harbor-registry`: Container images
- `harbor-chartmuseum`: Helm charts
- `harbor-jobservice`: Harbor job logs

**Backup Schedule**:
- Daily: 02:00 UTC (retention 7 days)
- On-demand: `velero backup create <name>`

**Documentação**: [MINIO_OPERATIONS.md](MINIO_OPERATIONS.md), [VELERO.md](VELERO.md)

---

### 3. Secrets Management Layer

| Componente | Versão | Finalidade | Status | NodePort |
|------------|--------|------------|--------|----------|
| **Vault** | 1.15+ | Centralized secrets | ✅ Instalado | 30820 |
| **External Secrets Operator** | 0.9+ | Vault → K8s sync | ✅ Instalado | - |

**Arquitetura**:
```
Vault (centralized, audited)
  ↓ Kubernetes Auth
External Secrets Operator
  ↓ Sync (polling 15min-1h)
K8s Secrets (native)
  ↓ Mount
Application Pods (transparent)
```

**Benefícios**:
- ✅ Secrets centralizados no Vault
- ✅ Aplicações usam Secrets nativos do K8s (sem mudanças)
- ✅ Rotação automática via ESO
- ✅ Audit logs no Vault

**Documentação**: [VAULT.md](VAULT.md)

---

### 4. Container Registry Layer

| Componente | Versão | Finalidade | Status | NodePort |
|------------|--------|------------|--------|----------|
| **Harbor** | 2.10+ | Private registry | ✅ Instalado | 30880 |
| **Trivy** | (embedded) | Vulnerability scanner | ✅ Instalado | - |

**Projetos**:

| Projeto | Finalidade | Branch Source | Retention | Block Vulns | Content Trust |
|---------|------------|---------------|-----------|-------------|---------------|
| **tst** | Staging | `develop` | 10 images / 30d | ❌ No | ❌ Optional |
| **prd** | Production | `main`/`master` | 20 images / 90d | ✅ Critical+ | ✅ Yes |

**Features**:
- ✅ Auto-scan com Trivy (todas as imagens)
- ✅ Retention policies (garbage collection automático)
- ✅ Robot accounts para CI/CD
- ✅ Webhooks para notificações
- ✅ Helm chart repository
- ✅ Replication (multi-cluster ready)

**Documentação**: [HARBOR.md](HARBOR.md)

---

### 5. Observability Layer

| Componente | Versão | Finalidade | Status | NodePort |
|------------|--------|------------|--------|----------|
| **Prometheus** | 2.50+ | Metrics collection | ✅ Instalado | 30090 |
| **Grafana** | 10.0+ | Dashboards | ✅ Instalado | 30030 |
| **Loki** | 2.9+ | Log aggregation | ✅ Instalado | 30310 |
| **Alertmanager** | 0.27+ | Alerting | ✅ Instalado | 30093 |

**Métricas Coletadas**:
- Node metrics (CPU, RAM, disk, network)
- Pod metrics (resource usage, restart counts)
- Application metrics (via annotations)
- Harbor metrics (registry operations)
- Vault metrics (secret operations)

**Dashboards Grafana**:
- Kubernetes Cluster Overview
- Node Exporter Full
- Pod Resource Usage
- Harbor Overview
- Loki Logs Browser

**Documentação**: Ver módulos `prometheus`, `grafana`, `loki`

---

### 6. CI/CD Layer

| Componente | Versão | Finalidade | Status | Acesso |
|------------|--------|------------|--------|--------|
| **Harness** | CE/Enterprise | Pipeline orchestration | ⏳ Próximo | Via delegate |
| **Semgrep** | Latest | SAST code scanning | 📖 Documentado | CLI no pipeline |

**Harness Delegate**:
- Instalado no namespace `harness`
- Conecta com Harness Cloud/On-prem
- Executa pipelines no cluster

**Semgrep Integration**:
- Roda no CI stage
- Detecta vulnerabilidades (OWASP Top 10)
- Detecta secrets hardcoded
- Detecta bad practices

**Documentação**: Ver [Security Scanning](#security-scanning) abaixo

---

## Fluxos de Deploy

### Fluxo TST (Staging)

```
┌─────────────────────────────────────────────────────────────┐
│  Developer: git push origin develop                         │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
     ┌───────────────┐
     │  GitHub/GitLab│
     └───────┬───────┘
             │ Webhook
             ▼
┌─────────────────────────────────────────────────────────────┐
│           HARNESS CI PIPELINE (TST)                         │
│                                                             │
│  [1] Checkout develop branch                               │
│       ↓                                                     │
│  [2] Semgrep SAST scan                                     │
│       • Rules: auto (security, best practices)             │
│       • Exit code: 0 (warning only)                        │
│       ↓                                                     │
│  [3] Run tests                                             │
│       • Unit tests                                         │
│       • Coverage report                                    │
│       ↓                                                     │
│  [4] Docker build                                          │
│       • Multi-stage build                                  │
│       • Layer caching                                      │
│       ↓                                                     │
│  [5] Trivy image scan                                      │
│       • Severity: HIGH,CRITICAL                            │
│       • Exit code: 0 (warning only)                        │
│       ↓                                                     │
│  [6] Docker push to Harbor                                 │
│       • Tag: harbor.asgard:30880/tst/myapp:dev-${BUILD_ID}│
│       • Harbor auto-scan with Trivy                        │
│       ↓                                                     │
│  [7] Trigger CD pipeline                                   │
└─────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│           HARNESS CD PIPELINE (TST)                         │
│                                                             │
│  [1] Get secrets from Vault                                │
│       • ExternalSecret syncs to K8s Secret                 │
│       • DB credentials, API keys, etc                      │
│       ↓                                                     │
│  [2] Update K8s manifests                                  │
│       • Set image: harbor.asgard:30880/tst/myapp:dev-123   │
│       • Set secrets references                             │
│       ↓                                                     │
│  [3] kubectl apply -f k8s/tst/                            │
│       • Deployment, Service, Ingress                       │
│       ↓                                                     │
│  [4] kubectl rollout status                                │
│       • Wait for pods Ready                                │
│       • Timeout: 5 minutes                                 │
│       ↓                                                     │
│  [5] Smoke tests                                           │
│       • HTTP health check                                  │
│       • Basic functionality test                           │
│       ↓                                                     │
│  [6] Notify                                                │
│       • Slack: "Deploy TST success ✅"                     │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo PRD (Production)

```
┌─────────────────────────────────────────────────────────────┐
│  Developer: git push origin main                            │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
     ┌───────────────┐
     │  GitHub/GitLab│
     └───────┬───────┘
             │ Webhook
             ▼
┌─────────────────────────────────────────────────────────────┐
│           HARNESS CI PIPELINE (PRD)                         │
│                                                             │
│  [1] Checkout main branch                                  │
│       ↓                                                     │
│  [2] Semgrep SAST scan                                     │
│       • Rules: auto (security, best practices)             │
│       • Exit code: 1 if errors found (BLOCK)               │
│       ↓                                                     │
│  [3] Run tests (MUST PASS)                                 │
│       • Unit tests                                         │
│       • Integration tests                                  │
│       • Coverage threshold: 80%                            │
│       ↓                                                     │
│  [4] Docker build                                          │
│       • Multi-stage build                                  │
│       • Layer caching                                      │
│       ↓                                                     │
│  [5] Trivy image scan (STRICT)                            │
│       • Severity: CRITICAL only                            │
│       • Exit code: 1 if CRITICAL found (BLOCK)             │
│       ↓                                                     │
│  [6] Docker push to Harbor                                 │
│       • Tag: harbor.asgard:30880/prd/myapp:v1.2.3         │
│       • Harbor auto-scan with Trivy                        │
│       • Harbor BLOCKS if CRITICAL vulnerabilities          │
│       ↓                                                     │
│  [7] Sign image (optional)                                 │
│       • Cosign sign                                        │
│       • Content trust validation                           │
│       ↓                                                     │
│  [8] Trigger CD pipeline (manual approval)                │
└─────────────────────────────────────────────────────────────┘
             │
             ▼ (Manual approval required)
┌─────────────────────────────────────────────────────────────┐
│           HARNESS CD PIPELINE (PRD)                         │
│                                                             │
│  [1] Get secrets from Vault                                │
│       • ExternalSecret syncs to K8s Secret                 │
│       • Production credentials                             │
│       ↓                                                     │
│  [2] Update K8s manifests                                  │
│       • Set image: harbor.asgard:30880/prd/myapp:v1.2.3   │
│       • Set secrets references                             │
│       • Set resource limits (production values)            │
│       ↓                                                     │
│  [3] kubectl apply -f k8s/prd/ (Blue-Green)              │
│       • Deploy new version (green)                         │
│       • Keep old version running (blue)                    │
│       ↓                                                     │
│  [4] kubectl rollout status                                │
│       • Wait for pods Ready                                │
│       • Timeout: 10 minutes                                │
│       ↓                                                     │
│  [5] Smoke tests + Integration tests                       │
│       • HTTP health check                                  │
│       • Database connectivity                              │
│       • External API calls                                 │
│       ↓                                                     │
│  [6] Switch traffic to green                               │
│       • Update Service selector                            │
│       • Monitor for 5 minutes                              │
│       ↓                                                     │
│  [7] Cleanup blue deployment                               │
│       • Scale down old version                             │
│       ↓                                                     │
│  [8] Notify + Tag release                                  │
│       • Slack: "Deploy PRD success ✅ v1.2.3"             │
│       • Git tag: v1.2.3                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Scanning

### Semgrep (SAST - Static Application Security Testing)

**O que é**: Ferramenta de análise estática de código que detecta vulnerabilidades, bugs e bad practices.

**Quando roda**: CI stage (antes do build)

**O que detecta**:
- ✅ Vulnerabilidades de segurança (SQL injection, XSS, etc)
- ✅ Secrets hardcoded (API keys, passwords)
- ✅ OWASP Top 10
- ✅ Best practices por linguagem
- ✅ Code quality issues

#### Instalação

```bash
# Via pip
pip install semgrep

# Via Docker
docker pull semgrep/semgrep

# Via Homebrew (macOS)
brew install semgrep
```

#### Uso no Pipeline

**GitHub Actions**:
```yaml
# .github/workflows/ci.yml
name: CI with Semgrep
on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Semgrep SAST Scan
        uses: semgrep/semgrep-action@v1
        with:
          config: auto  # Rules: security, best practices
          
      - name: Upload SARIF results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: semgrep.sarif
```

**Harness Pipeline**:
```yaml
# Harness CI stage
- step:
    type: Run
    name: Semgrep SAST
    identifier: semgrep_sast
    spec:
      shell: Bash
      command: |
        # Install Semgrep
        pip install semgrep
        
        # Run scan
        semgrep --config=auto \
          --json \
          --output=semgrep-report.json \
          --severity=ERROR \
          --severity=WARNING
        
        # Check for blocking errors
        ERRORS=$(jq '.errors | length' semgrep-report.json)
        if [ "$ERRORS" -gt 0 ]; then
          echo "❌ Semgrep found $ERRORS security issues"
          exit 1
        fi
```

**GitLab CI**:
```yaml
# .gitlab-ci.yml
semgrep:
  stage: security
  image: semgrep/semgrep
  script:
    - semgrep --config=auto --gitlab-sast --output=gl-sast-report.json
  artifacts:
    reports:
      sast: gl-sast-report.json
```

#### Rules Customizadas

```yaml
# semgrep.yml
rules:
  - id: hardcoded-password
    pattern: password = "..."
    message: Hardcoded password detected
    severity: ERROR
    languages: [python, javascript, go]
  
  - id: sql-injection
    pattern: |
      db.execute($SQL)
    message: Potential SQL injection
    severity: ERROR
    languages: [python]
```

Uso:
```bash
semgrep --config=semgrep.yml .
```

#### Integração com Harbor

Após Semgrep pass no CI:
1. Build image
2. Trivy scan da imagem
3. Push para Harbor
4. Harbor Trivy re-scan (confirmação)
5. Deploy se tudo OK

---

### Trivy (Container & Dependency Scanner)

**O que é**: Scanner de vulnerabilidades para containers, filesystems e git repositories.

**Quando roda**:
- CI stage (após build da imagem)
- Harbor (auto-scan após push)
- Scheduled scan (diário)

**O que detecta**:
- ✅ Vulnerabilidades em OS packages (Alpine, Debian, Ubuntu, etc)
- ✅ Vulnerabilidades em application dependencies (npm, pip, go.mod, etc)
- ✅ IaC misconfigurations (K8s manifests, Terraform)
- ✅ Secrets em images

#### Uso no Pipeline

**Scan de imagem**:
```bash
# Local
trivy image myapp:latest

# CI pipeline
trivy image --severity HIGH,CRITICAL --exit-code 1 myapp:latest
```

**Scan de código**:
```bash
# Filesystem scan
trivy fs --severity HIGH,CRITICAL .

# Git repository scan
trivy repo https://github.com/user/repo
```

**Integração Harness**:
```yaml
- step:
    type: Run
    name: Trivy Image Scan
    spec:
      command: |
        trivy image \
          --severity CRITICAL,HIGH \
          --exit-code 1 \
          --format json \
          --output trivy-report.json \
          harbor.asgard:30880/tst/myapp:${BUILD_ID}
```

#### Thresholds por Ambiente

| Ambiente | Severity | Exit Code | Ação |
|----------|----------|-----------|------|
| **TST** | HIGH,CRITICAL | 0 (warning) | Deploy anyway |
| **PRD** | CRITICAL | 1 (block) | Block deploy |

---

### Combinação Semgrep + Trivy

**Pipeline completo**:

```
[1] Semgrep (source code)
     ↓ Pass
[2] Build Docker image
     ↓
[3] Trivy (image + dependencies)
     ↓ Pass
[4] Push to Harbor
     ↓
[5] Harbor Trivy (re-scan)
     ↓ Pass (PRD: block if CRITICAL)
[6] Deploy to K8s
```

**Benefícios**:
- ✅ Semgrep: Detecta vulnerabilidades no código **antes** do build
- ✅ Trivy: Detecta vulnerabilidades na imagem **depois** do build
- ✅ Harbor: Confirma segurança no registry (re-scan periódico)
- ✅ Layers: 3 camadas de defesa

---

## Padrões TST vs PRD

### Tabela Comparativa

| Aspecto | TST (Staging) | PRD (Production) |
|---------|---------------|------------------|
| **Branch Source** | `develop` | `main`/`master` |
| **Auto-scan** | ✅ Yes (warning only) | ✅ Yes (blocking) |
| **Semgrep** | Exit 0 (warning) | Exit 1 (block) |
| **Trivy Threshold** | HIGH,CRITICAL (warning) | CRITICAL (block) |
| **Harbor Block Vulns** | ❌ No | ✅ Yes (CRITICAL) |
| **Content Trust** | ❌ Optional | ✅ Recommended |
| **Image Retention** | 10 images / 30 days | 20 images / 90 days |
| **Robot Permissions** | Push, Pull, Delete | Push, Pull |
| **Tag Immutability** | ❌ Mutable | ✅ Immutable |
| **Manual Approval** | ❌ No | ✅ Yes (before deploy) |
| **Deployment Strategy** | Rolling update | Blue-Green |
| **Health Check Timeout** | 5 minutes | 10 minutes |
| **Resource Limits** | Lower (cost optimization) | Higher (performance) |
| **Monitoring Alerts** | Low priority | High priority (PagerDuty) |
| **Backup** | ❌ Optional | ✅ Mandatory (Velero) |

---

## Integração entre Componentes

### 1. Harbor + Vault

**Use case**: Armazenar robot account tokens no Vault

```bash
# Criar robot account no Harbor UI → copiar token

# Armazenar no Vault
kubectl -n vault exec vault-0 -- \
  vault kv put secret/harbor/robot-tst \
    username=robot$cicd-tst \
    token=<HARBOR_TOKEN>

# Criar ExternalSecret para sincronizar
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: harbor-robot-tst
  namespace: harness
spec:
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: harbor-credentials-tst
  data:
  - secretKey: username
    remoteRef:
      key: secret/harbor/robot-tst
      property: username
  - secretKey: token
    remoteRef:
      key: secret/harbor/robot-tst
      property: token
EOF

# Usar no Harness pipeline
# Secret harbor-credentials-tst disponível no namespace harness
```

---

### 2. Harbor + Kubernetes

**Use case**: Deploy de imagens privadas do Harbor

```bash
# Criar imagePullSecret usando credenciais do Vault
kubectl create secret docker-registry harbor-pull-secret \
  --docker-server=192.168.1.81:30880 \
  --docker-username=robot$cicd-prd \
  --docker-password=$(kubectl -n vault exec vault-0 -- \
    vault kv get -field=token secret/harbor/robot-prd) \
  --namespace=production

# Ou via ExternalSecret (recomendado)
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: harbor-dockerconfig
  namespace: production
spec:
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: harbor-pull-secret
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "192.168.1.81:30880": {
                "username": "{{ .username }}",
                "password": "{{ .token }}",
                "auth": "{{ printf "%s:%s" .username .token | b64enc }}"
              }
            }
          }
  data:
  - secretKey: username
    remoteRef:
      key: secret/harbor/robot-prd
      property: username
  - secretKey: token
    remoteRef:
      key: secret/harbor/robot-prd
      property: token
EOF

# Usar no Deployment
spec:
  imagePullSecrets:
  - name: harbor-pull-secret
  containers:
  - image: 192.168.1.81:30880/prd/myapp:v1.0.0
```

---

### 3. Prometheus + Grafana + Loki

**Use case**: Observabilidade completa (metrics + logs)

**Grafana datasources** (já configurados):
- Prometheus: Métricas
- Loki: Logs
- Alertmanager: Alertas

**Dashboard exemplo** (importar no Grafana):
```json
{
  "dashboard": {
    "title": "Application Overview",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "datasource": "Prometheus"
          }
        ]
      },
      {
        "title": "Error Logs",
        "targets": [
          {
            "expr": "{namespace=\"production\"} |= \"error\"",
            "datasource": "Loki"
          }
        ]
      }
    ]
  }
}
```

---

### 4. Velero + MinIO

**Use case**: Backup automático do cluster

```bash
# Backup já configurado (daily at 02:00 UTC)
velero schedule get

# Backup manual antes de mudança crítica
velero backup create pre-upgrade-backup --wait

# Restore específico
velero restore create --from-backup daily-backup-20260202

# Restore apenas namespace production
velero restore create --from-backup daily-backup-20260202 \
  --include-namespaces production
```

---

## Guias de Implementação

### Ordem de Instalação Recomendada

1. ✅ **Infraestrutura base** (já instalado)
   - `kubernetes`, `calico`, `metallb`, `traefik`, `cert_manager`

2. ✅ **Storage** (já instalado)
   - `minio`, `velero`

3. ✅ **Secrets** (já instalado)
   - `vault`, `secrets` (External Secrets Operator)

4. ✅ **Observability** (já instalado)
   - `prometheus`, `grafana`, `loki`

5. ✅ **Registry** (recém-instalado)
   - `harbor`

6. ⏳ **CI/CD** (próximo passo)
   - `harness`

### Checklist de Produção

#### Infraestrutura
- [ ] Kubernetes cluster com 3+ nodes (HA)
- [ ] Network policies habilitadas
- [ ] Resource quotas configuradas por namespace
- [ ] Pod Security Standards (restricted)
- [ ] Ingress TLS com cert-manager

#### Storage & Backup
- [ ] MinIO com replicação (se multi-node)
- [ ] Velero backup testado (criar + restore)
- [ ] Retention policy configurada (7-30 dias)
- [ ] Backup offsite (copiar para S3/GCS externo)

#### Secrets
- [ ] Vault unsealed e funcional
- [ ] Root token e unseal keys em cofre físico
- [ ] Policies granulares por namespace
- [ ] ExternalSecrets sincronizando corretamente
- [ ] Testar rotação de secrets

#### Registry
- [ ] Harbor projetos tst/prd criados
- [ ] Robot accounts configurados
- [ ] Tokens armazenados no Vault
- [ ] Retention policies ativas
- [ ] Garbage collection agendado
- [ ] Vulnerability scan testado
- [ ] imagePullSecrets configurados nos namespaces

#### Observability
- [ ] Prometheus coletando métricas de todos os pods
- [ ] Grafana dashboards importados
- [ ] Loki agregando logs
- [ ] Alertmanager configurado (Slack/Email/PagerDuty)
- [ ] Alertas críticos testados

#### CI/CD
- [ ] Harness delegate instalado e conectado
- [ ] Pipelines CI/CD criados (tst/prd)
- [ ] Semgrep configurado no CI
- [ ] Trivy thresholds configurados
- [ ] Manual approval habilitado em PRD
- [ ] Rollback procedure documentada

#### Segurança
- [ ] Semgrep rules customizadas (se necessário)
- [ ] Trivy scanning em todos os estágios
- [ ] Harbor blocking vulnerabilities em PRD
- [ ] Network policies deny-by-default
- [ ] RBAC configurado (least privilege)
- [ ] Audit logs habilitados (K8s + Vault + Harbor)

---

## Troubleshooting Geral

### Cenário: Pipeline falha no Semgrep

```bash
# Ver detalhes do erro
semgrep --config=auto --verbose .

# Ignorar falso positivo
# Adicionar comment no código:
# nosemgrep: rule-id

# Ou criar .semgrepignore
echo "tests/" >> .semgrepignore
echo "vendor/" >> .semgrepignore
```

### Cenário: Trivy bloqueia deploy

```bash
# Ver vulnerabilidades detalhadas
trivy image --severity CRITICAL harbor.asgard:30880/prd/myapp:v1.0.0

# Whitelist CVE específico (Harbor UI)
Harbor → Projects → prd → Configuration → CVE Allowlist

# Ou atualizar base image
# FROM alpine:3.19 → FROM alpine:3.20
```

### Cenário: ExternalSecret não sincroniza

```bash
# Ver status
kubectl -n production get externalsecret myapp-secret
kubectl -n production describe externalsecret myapp-secret

# Ver logs do ESO
kubectl -n external-secrets logs deployment/external-secrets -f

# Testar acesso ao Vault manualmente
kubectl -n vault exec vault-0 -- vault kv get secret/myapp
```

### Cenário: Harbor push bloqueado

```bash
# Verificar scan results
Harbor UI → Projects → prd → Repositories → myapp → Vulnerabilities

# Temporariamente desabilitar (não recomendado)
Harbor UI → Projects → prd → Configuration
→ Prevent vulnerable images: OFF

# Solução: corrigir vulnerabilidades e rebuild
```

---

## Referências

### Documentação Oficial

- **Kubernetes**: https://kubernetes.io/docs/
- **Calico**: https://docs.tigera.io/calico/latest/
- **Traefik**: https://doc.traefik.io/traefik/
- **MinIO**: https://min.io/docs/
- **Vault**: https://www.vaultproject.io/docs
- **Harbor**: https://goharbor.io/docs/
- **Semgrep**: https://semgrep.dev/docs/
- **Trivy**: https://aquasecurity.github.io/trivy/
- **Harness**: https://docs.harness.io/
- **Velero**: https://velero.io/docs/

### Documentação Local

- [VAULT.md](VAULT.md) - Secrets management
- [HARBOR.md](HARBOR.md) - Container registry
- [VELERO.md](VELERO.md) - Backup/restore
- [MINIO_OPERATIONS.md](MINIO_OPERATIONS.md) - Object storage
- [INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md) - Setup geral

### Exemplos de Pipelines

Ver pasta `examples/ci-cd/` para:
- GitHub Actions workflows
- GitLab CI pipelines
- Harness pipeline examples
- Semgrep + Trivy integration

---

**Última atualização**: Fevereiro 2026
**Versão**: 1.0.0
**Status**: Production Ready ✅
