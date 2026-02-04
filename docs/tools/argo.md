# Argo — GitOps e CI/CD

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Kong](kong.md) | [Próximo: Módulos de Infraestrutura →](network.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Argo CD](#argo-cd)
- [Argo Workflows](#argo-workflows)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)

---

## O que é
- **[Argo](#1-argo)¹**: Suite CNCF para CI/CD e GitOps em Kubernetes.
- **[Argo CD](#2-argo-cd)²**: Continuous Delivery via GitOps (declarativo).
- **[Argo Workflows](#3-argo-workflows)³**: Engine de workflows para CI/pipelines complexos.

## Por que usamos
- **GitOps nativo**: Git como source of truth (não push manual).
- **Declarativo**: Manifests YAML versionados, auditáveis.
- **Multi-cluster**: Gerenciar múltiplos clusters de um Argo CD.
- **Rollback fácil**: Reverter para commit anterior no Git.

## Como está configurado no Raijin (V1)
- **Versões**:
  - Argo CD 2.10+ (Helm chart `argo/argo-cd`)
  - Argo Workflows 3.5+ (Helm chart `argo/argo-workflows`)
- **Namespaces**:
  - `argocd`: Argo CD
  - `argo`: Argo Workflows
- **Acesso**:
  - Argo CD UI: `https://argocd.local.io`
  - Argo Workflows UI: `https://argo.local.io`
- **Repositório**: GitHub/GitLab conectado via SSH key
- **Sync policy**: Manual (requer aprovação para deploy)

## Como operamos

### Argo CD

#### Login CLI

```bash
# Instalar argocd CLI
curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x /usr/local/bin/argocd

# Login
argocd login argocd.local.io --username admin --password <password>

# Ou via port-forward
kubectl port-forward -n argocd svc/argocd-server 8080:443
argocd login localhost:8080 --insecure
```

#### Criar Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/myapp
    targetRevision: main
    path: k8s/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: myapp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

#### Sync manual

```bash
# Via CLI
argocd app sync myapp

# Via UI
# Applications → myapp → Sync → Synchronize

# Force sync (ignora diff)
argocd app sync myapp --force
```

### Argo Workflows

#### Criar Workflow

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: build-
  namespace: argo
spec:
  entrypoint: build-and-push
  templates:
  - name: build-and-push
    steps:
    - - name: build
        template: docker-build
    - - name: push
        template: docker-push
  
  - name: docker-build
    container:
      image: docker:24
      command: [docker, build]
      args: ["-t", "myapp:{{workflow.parameters.version}}", "."]
      volumeMounts:
      - name: docker-sock
        mountPath: /var/run/docker.sock
  
  - name: docker-push
    container:
      image: docker:24
      command: [docker, push]
      args: ["myapp:{{workflow.parameters.version}}"]
```

#### Executar Workflow

```bash
# Instalar argo CLI
curl -sLO https://github.com/argoproj/argo-workflows/releases/latest/download/argo-linux-amd64.gz
gunzip argo-linux-amd64.gz
chmod +x argo-linux-amd64
mv argo-linux-amd64 /usr/local/bin/argo

# Submit workflow
argo submit -n argo workflow.yaml --watch

# Listar workflows
argo list -n argo

# Ver logs
argo logs -n argo <workflow-name>

# Delete workflow
argo delete -n argo <workflow-name>
```

## Argo CD

### Repos privados

```bash
# Adicionar repo via CLI
argocd repo add https://github.com/org/private-repo \
  --username git \
  --password <token>

# Ou SSH
argocd repo add git@github.com:org/private-repo.git \
  --ssh-private-key-path ~/.ssh/id_rsa
```

### Projects

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: production
  namespace: argocd
spec:
  description: Production applications
  sourceRepos:
  - https://github.com/org/*
  destinations:
  - namespace: '*'
    server: https://kubernetes.default.svc
  clusterResourceWhitelist:
  - group: '*'
    kind: '*'
```

### Sync Hooks

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      containers:
      - name: migration
        image: myapp:latest
        command: ["./migrate.sh"]
      restartPolicy: Never
```

## Argo Workflows

### WorkflowTemplate

```yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: ci-template
  namespace: argo
spec:
  entrypoint: ci
  templates:
  - name: ci
    steps:
    - - name: test
        template: run-tests
    - - name: build
        template: docker-build
    - - name: deploy
        template: kubectl-apply
  
  - name: run-tests
    container:
      image: golang:1.21
      command: [go, test, ./...]
```

### CronWorkflow

```yaml
apiVersion: argoproj.io/v1alpha1
kind: CronWorkflow
metadata:
  name: nightly-backup
  namespace: argo
spec:
  schedule: "0 2 * * *"  # 2 AM diariamente
  workflowSpec:
    entrypoint: backup
    templates:
    - name: backup
      container:
        image: postgres:15
        command: [pg_dump]
        args: ["-h", "postgres", "-U", "user", "db"]
```

## Troubleshooting

### Argo CD app OutOfSync

```bash
# Ver diff
argocd app diff myapp

# Ver status
argocd app get myapp

# Sync forçado
argocd app sync myapp --force --prune

# Logs do sync
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

### Argo CD não conecta ao Git

```bash
# Testar repo
argocd repo list

# Ver erro de conexão
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server

# Adicionar repo novamente
argocd repo add <repo-url> --username <user> --password <token>
```

### Argo Workflows stuck

```bash
# Ver status do workflow
argo get -n argo <workflow-name>

# Logs do step
argo logs -n argo <workflow-name> <pod-name>

# Terminar workflow travado
argo terminate -n argo <workflow-name>

# Delete forçado
argo delete -n argo <workflow-name> --force
```

## Glossário

### 1. Argo
**Argo**: Suite CNCF para workflows, CI/CD, eventos em Kubernetes.
- **[argoproj.github.io](https://argoproj.github.io/)**

### 2. Argo CD
**Argo CD**: Ferramenta GitOps para continuous delivery declarativa.
- **[argo-cd.readthedocs.io](https://argo-cd.readthedocs.io/)**

### 3. Argo Workflows
**Argo Workflows**: Engine de workflows para CI/CD pipelines complexos (DAG-based).
- **[argoproj.github.io/workflows](https://argoproj.github.io/workflows/)**

### 4. GitOps
**GitOps**: Paradigma onde Git é a source of truth; mudanças via pull requests.

### 5. Application
**Application**: CRD Argo CD que define o que deploy onde (repo + path + cluster).

### 6. Sync
**Sync**: Ação de aplicar manifests do Git no cluster (reconciliação).

### 7. Workflow
**Workflow**: CRD Argo Workflows que define DAG de steps/tasks.

### 8. Hook
**Hook**: Job executado em fase específica do sync (PreSync, Sync, PostSync).

### 9. Project
**Project**: Agrupamento lógico de Applications com políticas (RBAC, repos permitidos).

### 10. SelfHeal
**SelfHeal**: Argo CD automaticamente reverte mudanças manuais (drift detection).

---

## Exemplos práticos

### Instalar Argo CD

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

cat << EOF > argocd-values.yaml
server:
  ingress:
    enabled: true
    hosts:
    - argocd.local.io
    tls:
    - secretName: argocd-tls
      hosts:
      - argocd.local.io

configs:
  params:
    server.insecure: true  # TLS terminado no Ingress

redis-ha:
  enabled: false  # Single Redis para dev

repoServer:
  replicas: 1

controller:
  replicas: 1
EOF

helm install argocd argo/argo-cd \
  -n argocd \
  --create-namespace \
  -f argocd-values.yaml

# Senha inicial
kubectl get secret -n argocd argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

### Instalar Argo Workflows

```bash
cat << EOF > argo-workflows-values.yaml
server:
  ingress:
    enabled: true
    hosts:
    - argo.local.io
    tls:
    - secretName: argo-tls
      hosts:
      - argo.local.io

controller:
  workflowNamespaces:
  - argo
  - default

workflow:
  serviceAccount:
    create: true
  rbac:
    create: true
EOF

helm install argo-workflows argo/argo-workflows \
  -n argo \
  --create-namespace \
  -f argo-workflows-values.yaml
```

### Application com Kustomize

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/myapp
    targetRevision: main
    path: k8s/overlays/production
    kustomize:
      commonLabels:
        app: myapp
      images:
      - myapp=myapp:v1.2.3
  destination:
    server: https://kubernetes.default.svc
    namespace: myapp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

---

## Boas práticas ✅

1. **Git como source of truth**: Não fazer `kubectl apply` manual.
2. **Branches por ambiente**: `main` = prod, `staging` = staging.
3. **Automated sync com caution**: `prune: true` pode deletar recursos.
4. **Sync hooks para migrations**: PreSync para DB migrations.
5. **Projects para RBAC**: Separar prod/staging/dev.
6. **Secrets via External Secrets**: Não comitar secrets no Git.
7. **Health checks customizados**: Para CRDs complexos.
8. **Notifications**: Slack/webhook em sync failures.
9. **Rollback via Git revert**: Não via `kubectl rollout undo`.
10. **Workflows com retry**: Tolerar falhas transitórias.
11. **Artifact repository**: S3/MinIO para outputs de workflows.
12. **Resource limits em workflows**: Evitar OOMKilled.
13. **CronWorkflow para jobs periódicos**: Backups, cleanups.
14. **Logs centralizados**: Workflows → Loki.
15. **Monitorar Argo CD sync metrics**: Alertar em failures.

---

## Práticas ruins ❌

1. **Push manual**: `kubectl apply` ignorando GitOps.
2. **Secrets no Git**: Comitar passwords plaintext.
3. **AutoSync sem testar**: Quebrar prod automaticamente.
4. **Sem sync hooks**: Aplicar app antes de migration.
5. **Um branch para tudo**: Dificulta rollback por ambiente.
6. **Sem RBAC**: Todos com acesso admin no Argo CD.
7. **Health checks default**: CRDs customizados marcados unhealthy.
8. **Não versionar workflows**: Perder pipelines.
9. **Workflows sem limites**: Consumir toda RAM do cluster.
10. **Artifacts efêmeros**: Perder build outputs.
11. **CronWorkflow sem retry**: Jobs críticos falhando silenciosamente.
12. **Logs não preservados**: Debugar workflows antigos.
13. **Não monitorar sync**: Descobrir falhas tarde.
14. **Multiple sources of truth**: Git + kubectl apply = inconsistência.
15. **Não documentar hooks**: Hooks obscuros quebrando deploys.

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Kong](kong.md)** | **[Próximo: Módulos de Infraestrutura →](network.md)**
