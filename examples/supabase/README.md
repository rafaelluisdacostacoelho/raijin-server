# Supabase Examples

Este diretório contém exemplos de manifests Kubernetes para deploy do Supabase.

## Pré-requisitos

Antes de aplicar estes manifests, certifique-se de ter:

- **Kubernetes** cluster (v1.28+)
- **Traefik** Ingress Controller instalado
- **cert-manager** para gerenciamento de certificados TLS
- **MinIO** para armazenamento de arquivos (Storage API usa S3-compatible backend)

> **Nota**: O MinIO será automaticamente configurado com um bucket dedicado `supabase-storage` e um usuário com permissões mínimas quando usar o comando `raijin-server supabase install`.

## Estrutura

```
supabase/
├── README.md                          # Este arquivo
├── namespace.yaml                     # Namespace base
├── secrets/
│   ├── postgres-secret.yaml          # Credentials PostgreSQL
│   └── jwt-secret.yaml               # JWT keys
├── database/
│   ├── postgres-statefulset.yaml     # PostgreSQL StatefulSet
│   ├── postgres-service.yaml         # PostgreSQL Service
│   └── postgres-pvc.yaml             # PersistentVolumeClaim
├── services/
│   ├── kong-deployment.yaml          # Kong Gateway (Load Balancer)
│   ├── postgrest-deployment.yaml     # PostgREST (REST API)
│   ├── gotrue-deployment.yaml        # GoTrue (Auth)
│   ├── realtime-deployment.yaml      # Realtime (WebSocket)
│   └── storage-deployment.yaml       # Storage API
├── networking/
│   ├── ingress.yaml                  # Ingress com TLS
│   └── networkpolicy.yaml            # Network Policies
├── backup/
│   ├── velero-schedule.yaml          # Backup automático diário
│   └── postgres-backup-cronjob.yaml  # pg_dump CronJob
├── monitoring/
│   ├── servicemonitor.yaml           # Prometheus ServiceMonitor
│   └── prometheusrule.yaml           # Alertas
└── autoscaling/
    ├── hpa-kong.yaml                 # HPA para Kong
    ├── hpa-postgrest.yaml            # HPA para PostgREST
    └── pdb.yaml                      # PodDisruptionBudget

```

## Quick Start

### 1. Aplicar manifests base

```bash
# Namespace
kubectl apply -f namespace.yaml

# Secrets (ajuste os valores antes!)
kubectl apply -f secrets/

# Nota: O secret supabase-minio-credentials será criado automaticamente
# pelo comando 'raijin-server supabase install'. Se for aplicar manualmente,
# você precisa criar este secret com as credenciais do MinIO:
# - endpoint: http://minio.minio.svc:9000
# - bucket: supabase-storage
# - accessKeyId: <minio-user>
# - secretAccessKey: <minio-password>

# Database
kubectl apply -f database/

# Aguardar PostgreSQL ficar pronto
kubectl wait --for=condition=ready pod -l app=postgres -n supabase --timeout=300s

# Services
kubectl apply -f services/

# Networking
kubectl apply -f networking/
```

### 2. Configurar backup (opcional)

```bash
kubectl apply -f backup/velero-schedule.yaml
```

### 3. Configurar monitoring (opcional)

```bash
kubectl apply -f monitoring/
```

### 4. Configurar autoscaling (opcional)

```bash
kubectl apply -f autoscaling/
```

## Customização

### Ajustar réplicas

Edite os arquivos de deployment em `services/` e ajuste o campo `replicas:`.

Recomendações para produção:
- **Kong**: 2-4 réplicas
- **PostgREST**: 2-4 réplicas
- **GoTrue**: 2-3 réplicas
- **Realtime**: 2-3 réplicas
- **Storage**: 2 réplicas
- **PostgreSQL**: 1 réplica (StatefulSet)

### Ajustar storage

Edite `database/postgres-pvc.yaml` e ajuste o campo `storage:` conforme necessário.

### Ajustar domínio

O domínio está configurado para `supabase.cryptidnest.com`. Para usar outro domínio, edite `networking/ingress.yaml` e ajuste o campo `host:`.

## Integração com Lovable

Após deploy, obtenha as keys:

```bash
# Anon Key (pública)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.anonKey}' | base64 -d

# Service Role Key (privada)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.serviceKey}' | base64 -d
```

Configure no seu app Lovable:

```javascript
// .env.local
VITE_SUPABASE_URL=https://supabase.cryptidnest.com
VITE_SUPABASE_ANON_KEY=<anon-key-from-above>
```

## Verificação

```bash
# Ver status dos pods
kubectl get pods -n supabase

# Testar API
curl https://supabase.cryptidnest.com/rest/v1/

# Testar Auth
curl https://supabase.cryptidnest.com/auth/v1/health

# Ver logs Kong
kubectl logs -n supabase -l app=supabase-kong -f
```

## Troubleshooting

Ver documentação completa em `docs/tools/supabase.md`.
