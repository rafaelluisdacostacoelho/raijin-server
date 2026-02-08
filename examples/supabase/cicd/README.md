# Supabase CI/CD Configuration

Este diretório contém exemplos de configuração CI/CD para deploy automatizado do Supabase.

## Pré-requisitos no Cluster

Antes de configurar o CI/CD, verifique que o cluster Kubernetes tem:

- **Kubernetes** v1.28+
- **Traefik** Ingress Controller
- **cert-manager** para certificados TLS
- **MinIO** para armazenamento de arquivos
- **ArgoCD** (para GitOps) ou **GitHub Actions Runner** (para GitHub Actions)

> **Nota sobre MinIO**: O Supabase Storage API requer MinIO instalado. O comando `raijin-server supabase install` configura automaticamente um bucket dedicado e credenciais.

## Opções de CI/CD

### 1. Argo CD (GitOps) - Recomendado

Argo CD monitora o repositório Git e sincroniza automaticamente as mudanças no cluster.

```bash
# Aplicar Application do Argo CD
kubectl apply -f argocd-application.yaml

# Ver status
kubectl get application supabase -n argocd

# Forçar sync manual
argocd app sync supabase
```

**Vantagens**:
- ✅ GitOps completo
- ✅ Rollback fácil
- ✅ Auditoria automática
- ✅ Self-healing

### 2. GitHub Actions

Pipeline CI/CD completo com validação, testes e deploy.

**Setup**:

1. Adicione secrets no GitHub:
   ```
   KUBECONFIG_PRODUCTION  # kubeconfig em base64
   KUBECONFIG_TEST        # kubeconfig de teste em base64
   SLACK_WEBHOOK          # (opcional) para notificações
   ```

2. Copie o workflow:
   ```bash
   cp github-actions.yml .github/workflows/supabase-cicd.yml
   ```

3. Push para o repositório:
   ```bash
   git add .github/workflows/supabase-cicd.yml
   git commit -m "Add Supabase CI/CD"
   git push
   ```

**Features**:
- ✅ Validação de manifests
- ✅ Security scanning (Trivy)
- ✅ Deploy automático (test/prod)
- ✅ Health checks
- ✅ Rollback automático
- ✅ Notificações Slack

### 3. Argo Workflows

Pipeline de testes mais complexo antes do deploy.

```bash
# Aplicar Workflow
kubectl apply -f argo-workflow.yaml

# Executar manualmente
argo submit -n argo workflow-ci-supabase.yaml --watch

# Ver logs
argo logs -n argo @latest
```

## Estrutura Recomendada do Repositório

```
supabase-k8s/
├── .github/
│   └── workflows/
│       └── supabase-cicd.yml
├── manifests/
│   ├── namespace.yaml
│   ├── secrets/
│   ├── database/
│   ├── services/
│   ├── networking/
│   ├── backup/
│   ├── monitoring/
│   └── autoscaling/
├── migrations/
│   └── 001_initial_schema.sql
├── kustomization.yaml (opcional)
└── README.md
```

## Workflow GitOps Recomendado

```
1. Developer faz mudança no código
   ↓
2. Cria Pull Request
   ↓
3. GitHub Actions valida manifests e roda security scan
   ↓
4. Após aprovação, merge para main
   ↓
5. GitHub Actions faz backup (Velero)
   ↓
6. Argo CD detecta mudança no Git
   ↓
7. Argo CD aplica mudanças no cluster
   ↓
8. Health checks automáticos
   ↓
9. Notificação de sucesso/falha
```

## Melhores Práticas

### 1. Environments

Separe ambientes:
- **develop** branch → namespace `supabase-tst`
- **main** branch → namespace `supabase` (produção)

### 2. Secrets Management

Nunca commite secrets no Git! Use:
- **External Secrets Operator** + Vault
- **Sealed Secrets**
- GitHub Secrets (para kubeconfig)

```bash
# Criar sealed secret
kubeseal --format yaml < postgres-secret.yaml > postgres-sealed-secret.yaml
```

### 3. Validação Pré-Deploy

Sempre valide antes de aplicar:

```bash
# Dry-run
kubectl apply --dry-run=server -f manifests/

# Validar Kustomize
kubectl kustomize manifests/ | kubectl apply --dry-run=client -f -

# Security scan
trivy config manifests/ --severity HIGH,CRITICAL
```

### 4. Backup Antes de Deploy

```bash
# Criar backup antes de mudanças críticas
velero backup create supabase-pre-deploy-$(date +%Y%m%d) \
  --include-namespaces supabase \
  --wait
```

### 5. Rollback Plan

Sempre tenha um plano de rollback:

```bash
# Argo CD
argocd app rollback supabase

# Kubectl
kubectl rollout undo deployment/supabase-kong -n supabase

# Velero
velero restore create --from-backup supabase-backup-20260208
```

### 6. Monitoramento

Configure alertas para CI/CD:
- Deploy falhou
- Health check falhou
- Rollback automático executado

### 7. Tags e Versioning

Use tags semânticas:

```bash
git tag -a v1.0.0 -m "Initial Supabase deployment"
git push origin v1.0.0
```

Configure Argo CD para trackear tags:
```yaml
source:
  targetRevision: v1.0.0  # ao invés de 'main'
```

## Troubleshooting

### Argo CD não sincroniza

```bash
# Ver detalhes
argocd app get supabase

# Logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller

# Forçar refresh
argocd app sync supabase --force
```

### GitHub Actions falha no health check

```bash
# Verificar pods
kubectl get pods -n supabase

# Logs do Kong
kubectl logs -n supabase -l app=supabase-kong

# Events
kubectl get events -n supabase --sort-by=.lastTimestamp
```

### Argo Workflows não executa

```bash
# ServiceAccount tem permissões?
kubectl auth can-i create deployments --as=system:serviceaccount:argo:argo-workflow -n supabase

# Logs do workflow
argo logs -n argo <workflow-name>
```

## Recursos Adicionais

- [Argo CD Docs](https://argo-cd.readthedocs.io/)
- [GitHub Actions for Kubernetes](https://github.com/azure/setup-kubectl)
- [Argo Workflows](https://argoproj.github.io/argo-workflows/)
- [Velero Docs](https://velero.io/docs/)
