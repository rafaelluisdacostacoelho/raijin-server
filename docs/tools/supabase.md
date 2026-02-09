# Supabase — Open Source Firebase Alternative

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Argo](argo.md) | [→ Segurança](supabase-security.md)

---

## Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Alta Disponibilidade](#alta-disponibilidade)
- [Volumes Persistentes e Backup](#volumes-persistentes-e-backup)
- [Integração com Lovable](#integração-com-lovable)
- [Acesso Externo](#acesso-externo)
- [Monitoramento](#monitoramento)
- [Troubleshooting](#troubleshooting)
- [Boas e Más Práticas](#boas-e-más-práticas)

---

## Visão Geral

**Supabase** é uma alternativa open source ao **Firebase**, oferecendo:

### Recursos Principais

- ✅ **PostgreSQL Database**: Banco relacional completo com suporte a JSONB
- ✅ **PostgREST**: Auto-geração de API REST a partir do schema do banco
- ✅ **GoTrue**: Autenticação e autorização (JWT, OAuth, Magic Links)
- ✅ **Realtime**: WebSockets para subscriptions em tempo real
- ✅ **Storage**: Armazenamento de arquivos S3-compatible
- ✅ **Edge Functions**: Serverless functions (Deno)
- ✅ **Kong Gateway**: API Gateway com rate limiting e analytics
- ✅ **Studio**: Dashboard web para gerenciar dados e auth

### Componentes

```
Supabase Stack:
├── Kong Gateway (API Gateway + Load Balancer)
├── GoTrue (Auth Service)
├── PostgREST (REST API Generator)
├── Realtime (WebSocket Server)
├── Storage API (File Storage)
├── PostgreSQL (Database - StatefulSet)
├── pgBouncer (Connection Pooling)
└── Supabase Studio (Web UI)
```

---

## Arquitetura

### Arquitetura de Alta Disponibilidade

Para suportar múltiplas aplicações **Lovable** com dados centralizados:

```
┌────────────────────────────────────────────────────────────┐
│                    External Access Layer                   │
│     Lovable Apps → Traefik Ingress → TLS (cert-manager)    │
└────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────┐
│                      Supabase Layer                        │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Kong Gateway (Load Balancer)                        │  │
│  │  Deployment: 2-4 replicas                            │  │
│  │  Service: ClusterIP + NodePort/LoadBalancer          │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │                                      │
│   ┌─────────────────┼─────────────────┬──────────────┐     │
│   ▼                 ▼                 ▼              ▼     │
│  ┌────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   │
│  │GoTrue  │   │PostgREST │   │Realtime  │   │Storage   │   │
│  │2-4 pods│   │2-4 pods  │   │2-4 pods  │   │2-4 pods  │   │
│  └────┬───┘   └─────┬────┘   └─────┬────┘   └─────┬────┘   │
│       │             │              │              │        │
│       └─────────────┴──────────────┴──────────────┘        │
│                              ↓                             │
│          ┌───────────────────────────────────┐             │
│          │    pgBouncer (Connection Pool)    │             │
│          │    Deployment: 2 replicas         │             │
│          └───────────────┬───────────────────┘             │
│                          ↓                                 │
│          ┌───────────────────────────────────┐             │
│          │  PostgreSQL (StatefulSet)         │             │
│          │  Replica: 1 (Master)              │             │
│          │  PVC: 50Gi (Velero Backup)        │             │
│          └───────────────────────────────────┘             │
└────────────────────────────────────────────────────────────┘
```

### Fluxo de Requisições

```
Lovable App (Browser)
    ↓ HTTPS
Traefik Ingress (TLS)
    ↓
Kong Gateway (Pod 1/2/3/4) - Round Robin Load Balancing
    ↓
PostgREST/GoTrue/Realtime (Pods escalados 2-4x)
    ↓
pgBouncer (Connection Pooling)
    ↓
PostgreSQL StatefulSet (Master, PVC 50Gi)
```

**Vantagens desta arquitetura**:
- ✅ **Dados Centralizados**: Todos os apps Lovable compartilham o mesmo PostgreSQL
- ✅ **Alta Disponibilidade**: Serviços stateless escalados horizontalmente
- ✅ **Performance**: pgBouncer gerencia pool de conexões eficientemente
- ✅ **Backup Automático**: Velero faz backup do PVC do PostgreSQL
- ✅ **Zero Downtime**: Kong distribui carga entre pods saudáveis

---

## Instalação

### Pré-requisitos

- Kubernetes cluster funcionando
- **MinIO instalado** (para Storage API)
- Traefik ou NGINX Ingress instalado
- Cert-Manager para TLS automático
- Velero para backups (recomendado)
- ~8GB RAM disponível para stack completa
- StorageClass com suporte a ReadWriteOnce (PVC)

### Instalação via raijin-server

```bash
raijin-server install supabase
```

**Prompts**:
- `Namespace`: `supabase` (padrão)
- `Domínio externo`: `supabase.yourdomain.com`
- `PostgreSQL Storage Size`: `50Gi` (padrão)
- `Número de réplicas Kong`: `2` (2-4 recomendado)
- `Número de réplicas PostgREST`: `2`
- `Número de réplicas GoTrue`: `2`
- `Número de réplicas Realtime`: `2`
- `JWT Secret`: (gerado automaticamente)
- `PostgreSQL Password`: (gerado automaticamente)
- `Integrar com Velero`: `yes` (recomendado)

### O que é instalado

1. **PostgreSQL StatefulSet**
   - 1 replica (master)
   - PVC 50Gi com backup Velero
   - Configurações otimizadas para produção

2. **pgBouncer Deployment**
   - 2 replicas para HA
   - Connection pooling otimizado

3. **Supabase Services** (cada um 2-4 replicas)
   - Kong Gateway (API Gateway)
   - GoTrue (Authentication)
   - PostgREST (REST API)
   - Realtime (WebSocket)
   - Storage API (File uploads via MinIO)

4. **Supabase Studio**
   - 1 replica (UI dashboard)
   - Acesso interno apenas (via port-forward)

5. **MinIO Integration**
   - Bucket `supabase-storage` criado automaticamente
   - Usuário `supabase-storage-user` com permissões least-privilege
   - Credenciais salvas em secret `supabase-minio-credentials`

6. **Ingress com TLS**
   - Certificate automático via cert-manager
   - Roteamento para Kong Gateway

7. **Velero Backup Schedule**
   - Backup diário do namespace `supabase`
   - Retenção de 30 dias
   - Backup específico do PVC PostgreSQL

---

## Configuração

### Secrets

```yaml
# PostgreSQL credentials
apiVersion: v1
kind: Secret
metadata:
  name: supabase-postgres
  namespace: supabase
stringData:
  username: postgres
  password: <generated>
  database: postgres
```

```yaml
# JWT Secret for API authentication
apiVersion: v1
kind: Secret
metadata:
  name: supabase-jwt
  namespace: supabase
stringData:
  anonKey: <generated>
  serviceKey: <generated>
  secret: <generated>
```

```yaml
# MinIO credentials for Storage API
apiVersion: v1
kind: Secret
metadata:
  name: supabase-minio-credentials
  namespace: supabase
stringData:
  accessKeyId: <generated>
  secretAccessKey: <generated>
  endpoint: "minio.minio.svc:9000"
  bucket: "supabase-storage"
```

### ConfigMap de Conexão

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: supabase-config
  namespace: supabase
data:
  postgres-host: "postgres.supabase.svc.cluster.local"
  postgres-port: "5432"
  kong-http-port: "8000"
  kong-https-port: "8443"
  api-external-url: "https://supabase.yourdomain.com"
  storage-backend: "s3"
  minio-endpoint: "minio.minio.svc:9000"
```

### Variáveis de Ambiente

Cada serviço recebe as configurações necessárias:

```yaml
# GoTrue (Auth)
env:
  - name: GOTRUE_DB_DATABASE_URL
    value: "postgresql://postgres:$(POSTGRES_PASSWORD)@postgres:5432/postgres"
  - name: GOTRUE_JWT_SECRET
    valueFrom:
      secretKeyRef:
        name: supabase-jwt
        key: secret
  - name: GOTRUE_SITE_URL
    value: "https://supabase.yourdomain.com"
```

---

## Alta Disponibilidade

### Escalando Serviços Stateless

Todos os serviços **exceto PostgreSQL** podem ser escalados horizontalmente:

```bash
# Escalar Kong Gateway para 4 replicas
kubectl scale deployment supabase-kong -n supabase --replicas=4

# Escalar PostgREST
kubectl scale deployment supabase-postgrest -n supabase --replicas=4

# Escalar GoTrue
kubectl scale deployment supabase-gotrue -n supabase --replicas=3

# Escalar Realtime
kubectl scale deployment supabase-realtime -n supabase --replicas=3
```

### HorizontalPodAutoscaler (HPA)

Para auto-scaling baseado em CPU:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: supabase-postgrest-hpa
  namespace: supabase
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: supabase-postgrest
  minReplicas: 2
  maxReplicas: 8
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### PodDisruptionBudget

Para garantir disponibilidade durante updates:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: supabase-kong-pdb
  namespace: supabase
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: supabase-kong
```

---

## Volumes Persistentes e Backup

### PostgreSQL PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: supabase
  labels:
    app: postgres
    backup: velero
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path  # ou sua StorageClass
  resources:
    requests:
      storage: 50Gi
```

### Backup via Velero

#### Backup Schedule Automático

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: supabase-daily-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"  # 2 AM diariamente
  template:
    includedNamespaces:
      - supabase
    ttl: 720h  # 30 dias
    storageLocation: default
    volumeSnapshotLocations:
      - default
```

#### Backup Manual

```bash
# Backup completo do namespace
velero backup create supabase-backup-$(date +%Y%m%d) \
  --include-namespaces supabase \
  --wait

# Backup apenas do PVC do PostgreSQL
velero backup create supabase-postgres-pvc-$(date +%Y%m%d) \
  --include-namespaces supabase \
  --include-resources pvc,pv \
  --selector app=postgres \
  --wait
```

#### Restore

```bash
# Listar backups disponíveis
velero backup get

# Restaurar
velero restore create --from-backup supabase-backup-20260208 --wait

# Restaurar apenas o PostgreSQL
velero restore create postgres-restore \
  --from-backup supabase-postgres-pvc-20260208 \
  --include-resources pvc,pv \
  --wait
```

### Snapshot Manual do PostgreSQL

Para backups adicionais de segurança:

```bash
# Exec no pod do PostgreSQL
kubectl exec -n supabase postgres-0 -- pg_dump -U postgres postgres > backup.sql

# Ou via CronJob
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: supabase
spec:
  schedule: "0 3 * * *"  # 3 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15
            env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: supabase-postgres
                  key: password
            command:
            - /bin/sh
            - -c
            - |
              pg_dump -h postgres.supabase.svc -U postgres postgres | \
              gzip > /backup/postgres-$(date +\%Y\%m\%d-\%H\%M\%S).sql.gz
            volumeMounts:
            - name: backup-storage
              mountPath: /backup
          restartPolicy: OnFailure
          volumes:
          - name: backup-storage
            persistentVolumeClaim:
              claimName: postgres-backups
```

---

## Integração com Lovable

### Configurando Aplicação Lovable

No seu app Lovable, configure as seguintes variáveis de ambiente:

```javascript
// .env.local
VITE_SUPABASE_URL=https://supabase.yourdomain.com
VITE_SUPABASE_ANON_KEY=<anon-key-from-secret>
```

### Obter as Keys

```bash
# Anon Key (pública - pode ser exposta no frontend)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.anonKey}' | base64 -d

# Service Role Key (privada - apenas backend)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.serviceKey}' | base64 -d
```

### Exemplo de Cliente Supabase

```typescript
// lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

### Exemplo de Uso

```typescript
// Autenticação
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'secure-password'
})

// Query de dados
const { data: posts } = await supabase
  .from('posts')
  .select('*')
  .order('created_at', { ascending: false })

// Realtime subscription
const channel = supabase
  .channel('public:posts')
  .on('postgres_changes', 
    { event: '*', schema: 'public', table: 'posts' },
    (payload) => console.log('Change received!', payload)
  )
  .subscribe()
```

### Network Policies (Segurança)

Para restringir acesso apenas de namespaces autorizados:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: supabase-ingress
  namespace: supabase
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: traefik  # Apenas Traefik
    - namespaceSelector:
        matchLabels:
          environment: production  # Apps autorizados
    ports:
    - protocol: TCP
      port: 8000
```

---

## Acesso Externo

### Ingress com TLS

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: supabase-ingress
  namespace: supabase
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - supabase.yourdomain.com
    secretName: supabase-tls
  rules:
  - host: supabase.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: supabase-kong
            port:
              number: 8000
```

### DNS Configuration

```bash
# A Record apontando para LoadBalancer IP ou NodePort
supabase.yourdomain.com.  IN  A  192.168.1.100

# Ou CNAME para LoadBalancer hostname
supabase.yourdomain.com.  IN  CNAME  traefik-lb.cluster.local.
```

### Testar Conectividade

```bash
# Testar API
curl https://supabase.yourdomain.com/rest/v1/

# Testar autenticação
curl https://supabase.yourdomain.com/auth/v1/health

# Testar realtime
curl https://supabase.yourdomain.com/realtime/v1/health
```

---

## Monitoramento

### ServiceMonitor (Prometheus)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: supabase-postgres
  namespace: supabase
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app: postgres
  endpoints:
  - port: metrics
    interval: 30s
```

### Grafana Dashboards

Dashboards recomendados:
- **PostgreSQL**: Dashboard ID `9628` (PostgreSQL Database)
- **Kong**: Dashboard ID `7424` (Kong Official)
- **Kubernetes**: Dashboard ID `15759` (Kubernetes Cluster Monitoring)

```bash
# Import dashboards
kubectl apply -f examples/supabase/grafana-dashboards.yaml
```

### Alertas

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: supabase-alerts
  namespace: supabase
spec:
  groups:
  - name: supabase
    interval: 30s
    rules:
    - alert: PostgreSQLDown
      expr: up{job="postgres"} == 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "PostgreSQL is down"
        description: "PostgreSQL in namespace supabase is down"
    
    - alert: PostgreSQLHighConnections
      expr: pg_stat_database_numbackends{datname="postgres"} > 80
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "PostgreSQL high connections"
        description: "PostgreSQL has {{ $value }} connections"
    
    - alert: SupabaseKongDown
      expr: up{job="supabase-kong"} == 0
      for: 2m
      labels:
        severity: critical
      annotations:
        summary: "Kong Gateway is down"
```

### Health Checks

```bash
# PostgreSQL
kubectl exec -n supabase postgres-0 -- pg_isready -U postgres

# Kong
kubectl exec -n supabase deploy/supabase-kong -- kong health

# PostgREST
kubectl exec -n supabase deploy/supabase-postgrest -- wget -qO- localhost:3000/

# GoTrue
kubectl exec -n supabase deploy/supabase-gotrue -- wget -qO- localhost:9999/health
```

---

## Troubleshooting

### Pods Não Iniciam

```bash
# Verificar eventos
kubectl get events -n supabase --sort-by=.lastTimestamp

# Logs do PostgreSQL
kubectl logs -n supabase postgres-0 --tail=100 -f

# Logs do Kong
kubectl logs -n supabase -l app=supabase-kong --tail=100 -f

# Descrever pod com problema
kubectl describe pod -n supabase <pod-name>
```

### Problemas de Conexão

```bash
# Testar conectividade PostgreSQL
kubectl run -n supabase psql-test --rm -it --restart=Never \
  --image=postgres:15 -- \
  psql -h postgres.supabase.svc -U postgres -c "SELECT version();"

# Testar porta do Kong
kubectl run -n supabase curl-test --rm -it --restart=Never \
  --image=curlimages/curl -- \
  curl -v http://supabase-kong.supabase.svc:8000/
```

### PVC Não Provisiona

```bash
# Verificar StorageClass
kubectl get storageclass

# Verificar PVC status
kubectl get pvc -n supabase

# Logs do provisioner
kubectl logs -n kube-system -l app=local-path-provisioner
```

### Performance Lenta

```bash
# Ver uso de recursos
kubectl top pods -n supabase

# Verificar conexões PostgreSQL
kubectl exec -n supabase postgres-0 -- psql -U postgres -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Ver queries lentas
kubectl exec -n supabase postgres-0 -- psql -U postgres -c \
  "SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
   FROM pg_stat_activity 
   WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 seconds';"
```

### Backup Falhou

```bash
# Verificar logs do Velero
velero backup logs supabase-backup-20260208

# Descrever backup
velero backup describe supabase-backup-20260208

# Verificar se MinIO/S3 está acessível
kubectl logs -n velero -l name=velero
```

---

## Boas e Más Práticas

### ✅ Boas Práticas

1. **Sempre usar TLS**
   - Configure cert-manager para HTTPS automático
   - Nunca exponha Supabase sem TLS em produção

2. **Rotacionar secrets regularmente**
   ```bash
   # Gerar novo JWT secret
   kubectl create secret generic supabase-jwt-new \
     --from-literal=secret=$(openssl rand -base64 32) -n supabase
   ```

3. **Backups múltiplos**
   - Velero para PVC (diário)
   - pg_dump para SQL dumps (diário)
   - Testar restore mensalmente

4. **Monitoramento proativo**
   - Configure alerts para PostgreSQL connections
   - Monitor CPU/Memory dos pods
   - Track API latency no Kong

5. **Resource Limits**
   ```yaml
   resources:
     requests:
       cpu: 500m
       memory: 512Mi
     limits:
       cpu: 2000m
       memory: 2Gi
   ```

6. **Network Policies**
   - Restrinja acesso ao PostgreSQL apenas para pods Supabase
   - Use namespaces separados para ambientes (tst/prd)

7. **Row Level Security (RLS)**
   - SEMPRE habilite RLS nas tabelas
   ```sql
   ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
   
   CREATE POLICY "Users can view own posts"
   ON posts FOR SELECT
   USING (auth.uid() = user_id);
   ```

### ❌ Más Práticas

1. **Não escalar PostgreSQL horizontalmente sem replicação**
   - PostgreSQL StatefulSet deve ter 1 replica
   - Para HA, use streaming replication (complexo)

2. **Não usar serviceKey no frontend**
   - serviceKey bypassa RLS
   - Apenas anonKey no frontend

3. **Não fazer queries N+1**
   ```typescript
   // ❌ Ruim
   const posts = await supabase.from('posts').select('*')
   for (const post of posts.data) {
     const author = await supabase.from('users').select('*').eq('id', post.user_id)
   }
   
   // ✅ Bom
   const posts = await supabase
     .from('posts')
     .select('*, users(*)')
   ```

4. **Não ignorar backups**
   - Backups automáticos são essenciais
   - Teste restore regularmente

5. **Não expor Studio publicamente**
   - Studio deve ser interno apenas
   - Use `kubectl port-forward` para acesso

6. **Não usar senhas fracas**
   - PostgreSQL password mínimo 32 caracteres
   - JWT secret mínimo 32 bytes random

---

## Próximos Passos

- [ ] **Replicação PostgreSQL**: Considere Patroni/Stolon para HA
- [ ] **Edge Functions**: Configure Deno edge functions
- [ ] **Observability**: Integre Loki para logs centralizados
- [ ] **Disaster Recovery**: Documente plano de DR completo
- [ ] **Performance Tuning**: Ajuste parâmetros PostgreSQL para workload

---

## Glossário

- **StatefulSet**: Workload do Kubernetes para aplicações stateful (como bancos de dados)
- **PVC**: PersistentVolumeClaim - requisição de storage persistente
- **pgBouncer**: Connection pooler para PostgreSQL
- **RLS**: Row Level Security - controle de acesso granular no Postgres
- **JWT**: JSON Web Token - usado para autenticação
- **PostgREST**: Gera API REST automaticamente a partir do schema Postgres
- **GoTrue**: Serviço de autenticação do Supabase
- **Kong**: API Gateway open source

---

**Dúvidas? Contribuições?**
- 📖 [Supabase Docs](https://supabase.com/docs)
- 🐙 [Supabase GitHub](https://github.com/supabase/supabase)
- 💬 [Comunidade Supabase](https://github.com/supabase/supabase/discussions)
