# Supabase Repository Structure

Este é um exemplo de estrutura de repositório Git para gerenciar o Supabase via GitOps (ArgoCD).

## Pré-requisitos no Cluster

Antes de fazer o deploy do Supabase, certifique-se que o cluster tem:

- **Kubernetes** v1.28+
- **Traefik** Ingress Controller
- **cert-manager** para certificados TLS
- **MinIO** para armazenamento de arquivos (Storage API)
- **Velero** (opcional) para backups
- **Prometheus** (opcional) para monitoring

> **Nota**: Se usar o comando `raijin-server supabase install`, o MinIO será automaticamente configurado com um bucket dedicado `supabase-storage` e um usuário com permissões mínimas.

## Estrutura Recomendada

```
supabase-k8s/
├── README.md                           # Documentação principal
├── .github/
│   └── workflows/
│       └── supabase-cicd.yml          # GitHub Actions
├── .gitignore                          # Ignora secrets locais
├── manifests/                          # Kubernetes manifests
│   ├── namespace.yaml
│   ├── secrets/
│   │   ├── postgres-secret.yaml
│   │   ├── jwt-secret.yaml
│   │   └── minio-secret.yaml          # MinIO credentials (auto-criado)
│   ├── database/
│   │   ├── postgres-pvc.yaml
│   │   ├── postgres-service.yaml
│   │   └── postgres-statefulset.yaml
│   ├── services/
│   │   ├── kong-deployment.yaml
│   │   ├── postgrest-deployment.yaml
│   │   ├── gotrue-deployment.yaml
│   │   ├── realtime-deployment.yaml
│   │   └── storage-deployment.yaml     # Usa MinIO S3 backend
│   ├── networking/
│   │   ├── ingress.yaml
│   │   └── networkpolicy.yaml
│   ├── backup/
│   │   ├── velero-schedule.yaml
│   │   └── postgres-backup-cronjob.yaml
│   ├── monitoring/
│   │   ├── servicemonitor.yaml
│   │   └── prometheusrule.yaml
│   └── autoscaling/
│       ├── hpa-kong.yaml
│       ├── hpa-postgrest.yaml
│       └── pdb.yaml
├── kustomization.yaml (opcional)      # Kustomize overlay
├── migrations/ (opcional)              # SQL migrations
│   └── 001_initial_schema.sql
└── scripts/
    ├── deploy.sh
    ├── rollback.sh
    └── backup.sh
```

## Inicialização do Repositório

### 1. Criar repositório
```bash
mkdir supabase-k8s
cd supabase-k8s
git init
```

### 2. Copiar manifests de exemplo

```bash
# Copiar exemplos do raijin-server
cp -r /path/to/raijin-server/examples/supabase/* ./manifests/
```

### 3. Configurar secrets (IMPORTANTE!)

**⚠️ NUNCA commite secrets reais no Git!**

Use uma das opções:

#### Opção A: Sealed Secrets (Recomendado)
```bash
# Instalar kubeseal
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/kubeseal-0.24.0-linux-amd64.tar.gz
tar -xzf kubeseal-0.24.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal

# Selar secrets
kubeseal --format yaml < manifests/secrets/postgres-secret.yaml > manifests/secrets/postgres-sealed-secret.yaml
kubeseal --format yaml < manifests/secrets/jwt-secret.yaml > manifests/secrets/jwt-sealed-secret.yaml

# Commite apenas os sealed secrets
git add manifests/secrets/*-sealed-secret.yaml
```

#### Opção B: External Secrets + Vault
```yaml
# manifests/secrets/external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: supabase-secrets
  namespace: supabase
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: supabase-postgres
  data:
    - secretKey: password
      remoteRef:
        key: supabase/postgres
        property: password
```

#### Opção C: Manual (apenas para desenvolvimento)
```bash
# Crie secrets diretamente no cluster (não versionados no Git)
kubectl create secret generic supabase-postgres \
  --from-literal=username=postgres \
  --from-literal=password=$(openssl rand -base64 32) \
  -n supabase

# Adicione ao .gitignore
echo "manifests/secrets/*-secret.yaml" >> .gitignore
```

### 4. Customizar manifests

Edite os arquivos para seu ambiente:
- **Domain**: `manifests/networking/ingress.yaml`
- **Storage size**: `manifests/database/postgres-pvc.yaml`
- **Replicas**: arquivos em `manifests/services/`
- **Storage class**: `manifests/database/postgres-pvc.yaml`

### 5. Criar .gitignore

```bash
cat > .gitignore <<EOF
# Secrets não selados
manifests/secrets/*-secret.yaml
!manifests/secrets/*-sealed-secret.yaml

# Kubeconfig local
kubeconfig
*.kubeconfig

# Backups locais
backups/
*.sql
*.sql.gz

# OS
.DS_Store
Thumbs.db
EOF
```

### 6. Primeiro commit

```bash
git add .
git commit -m "Initial Supabase manifests"
git branch -M main
git remote add origin https://github.com/your-org/supabase-k8s.git
git push -u origin main
```

## Deploy Inicial

### Via raijin-server (Recomendado)
```bash
raijin-server install supabase
```

### Via kubectl (Manual)
```bash
# Aplicar em ordem
kubectl apply -f manifests/namespace.yaml
kubectl apply -f manifests/secrets/
kubectl apply -f manifests/database/
kubectl wait --for=condition=ready pod -l app=postgres -n supabase --timeout=300s
kubectl apply -f manifests/services/
kubectl apply -f manifests/networking/
kubectl apply -f manifests/backup/
kubectl apply -f manifests/monitoring/
kubectl apply -f manifests/autoscaling/
```

### Via Argo CD (GitOps)
```bash
# Criar Application no Argo CD
kubectl apply -f manifests/argocd-application.yaml

# Verificar sync
argocd app get supabase
argocd app sync supabase
```

## Fluxo GitOps

### 1. Desenvolvimento Local
```bash
# Fazer mudanças
vim manifests/services/kong-deployment.yaml

# Validar
kubectl apply --dry-run=server -f manifests/

# Commit e push
git add manifests/services/kong-deployment.yaml
git commit -m "Scale Kong to 4 replicas"
git push
```

### 2. Argo CD Detecta Mudança
- Argo CD faz polling do repositório (default: 3 min)
- Detecta drift entre Git e cluster
- Aplica mudanças automaticamente (se auto-sync habilitado)

### 3. Verificação
```bash
# Via ArgoCD
argocd app get supabase

# Via kubectl
kubectl get pods -n supabase
```

## Scripts Úteis

### deploy.sh
```bash
#!/bin/bash
set -e

echo "Deploying Supabase..."
kubectl apply -f manifests/

echo "Waiting for rollout..."
kubectl rollout status deployment/supabase-kong -n supabase
kubectl rollout status deployment/supabase-postgrest -n supabase

echo "✓ Deploy completed"
```

### backup.sh
```bash
#!/bin/bash
set -e

BACKUP_NAME="supabase-backup-$(date +%Y%m%d-%H%M%S)"

echo "Creating backup: $BACKUP_NAME"
velero backup create $BACKUP_NAME \
  --include-namespaces supabase \
  --wait

echo "✓ Backup created: $BACKUP_NAME"
velero backup describe $BACKUP_NAME
```

### rollback.sh
```bash
#!/bin/bash
set -e

echo "Rolling back Supabase deployments..."
kubectl rollout undo deployment/supabase-kong -n supabase
kubectl rollout undo deployment/supabase-postgrest -n supabase
kubectl rollout undo deployment/supabase-gotrue -n supabase

echo "✓ Rollback completed"
```

## Makefile (Opcional)

```makefile
.PHONY: validate deploy backup rollback logs

validate:
	kubectl apply --dry-run=server -f manifests/
	trivy config manifests/

deploy:
	kubectl apply -f manifests/
	kubectl rollout status deployment/supabase-kong -n supabase --timeout=300s

backup:
	velero backup create supabase-backup-$$(date +%Y%m%d-%H%M%S) \
		--include-namespaces supabase \
		--wait

rollback:
	kubectl rollout undo deployment/supabase-kong -n supabase
	kubectl rollout undo deployment/supabase-postgrest -n supabase
	kubectl rollout undo deployment/supabase-gotrue -n supabase

logs:
	kubectl logs -n supabase -l app=supabase-kong -f
```

## Ambientes Múltiplos

### Estrutura para TST/PRD
```
supabase-k8s/
├── base/                    # Manifests base
│   └── ...
├── overlays/
│   ├── tst/
│   │   ├── kustomization.yaml
│   │   └── patches/
│   └── prd/
│       ├── kustomization.yaml
│       └── patches/
└── argocd/
    ├── application-tst.yaml
    └── application-prd.yaml
```

### Kustomization para TST
```yaml
# overlays/tst/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: supabase-tst

bases:
  - ../../base

patches:
  - path: patches/replicas.yaml
  - path: patches/ingress.yaml

commonLabels:
  environment: test
```

## Troubleshooting

### ArgoCD não sincroniza
```bash
# Verificar status
argocd app get supabase --show-params

# Forçar refresh
argocd app sync supabase --force

# Ver diff
argocd app diff supabase
```

### Secrets não funcionam
```bash
# Verificar secrets
kubectl get secrets -n supabase
kubectl describe secret supabase-postgres -n supabase

# Recriar sealed secret
kubeseal --format yaml < postgres-secret.yaml | kubectl apply -f -
```

### PostgreSQL não inicia
```bash
# Logs
kubectl logs -n supabase postgres-0

# Events
kubectl describe statefulset postgres -n supabase

# PVC
kubectl get pvc -n supabase
kubectl describe pvc postgres-data -n supabase
```

## Referências

- [Argo CD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [Kustomize](https://kustomize.io/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
- [External Secrets](https://external-secrets.io/)
- [Supabase Self-Hosting](https://supabase.com/docs/guides/self-hosting)
