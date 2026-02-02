# Velero - Backup e Restore do Kubernetes

## Visão Geral

Velero é uma ferramenta de backup e restore para clusters Kubernetes. No ambiente Raijin, está configurado para usar **MinIO** como storage backend S3-compatible.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Cluster Kubernetes                        │
│  ┌─────────────┐     ┌─────────────┐     ┌───────────────┐  │
│  │   Velero    │────▶│   MinIO     │────▶│ velero-backups│  │
│  │  (velero)   │     │   (minio)   │     │    bucket     │  │
│  └─────────────┘     └─────────────┘     └───────────────┘  │
│        │                                                     │
│        ▼                                                     │
│  ┌─────────────┐                                             │
│  │ node-agent  │  (para backup de PersistentVolumes)        │
│  │ (DaemonSet) │                                             │
│  └─────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

## Configuração Atual

| Componente | Valor |
|------------|-------|
| Storage Backend | MinIO (S3-compatible) |
| Bucket | `velero-backups` |
| S3 URL (interno) | `http://minio.minio.svc:9000` |
| Região | `minio` |
| Plugin | `velero/velero-plugin-for-aws:v1.8.0` |
| Node Agent | Habilitado (para PV backups) |
| Schedule | Diário às 02:00 UTC |
| Retenção | 7 dias (168h) |

## Comandos Essenciais

### Listar Backups

```bash
velero backup get
```

### Criar Backup Manual

```bash
# Backup completo (sem snapshots de volumes)
velero backup create meu-backup --snapshot-volumes=false --wait

# Backup de namespace específico
velero backup create ns-backup --include-namespaces=minha-app --snapshot-volumes=false --wait

# Backup com label selector
velero backup create app-backup --selector app=minha-app --wait
```

### Verificar Status de Backup

```bash
velero backup describe meu-backup --details
velero backup logs meu-backup
```

### Restaurar Backup

```bash
# Restore completo
velero restore create --from-backup meu-backup --wait

# Restore de namespace específico
velero restore create --from-backup meu-backup --include-namespaces=minha-app --wait

# Restore com novo nome de namespace
velero restore create --from-backup meu-backup --namespace-mappings old-ns:new-ns --wait
```

### Gerenciar Schedules

```bash
# Listar schedules
velero schedule get

# Criar schedule (diário às 3h, retenção 7 dias)
velero schedule create weekly-backup \
  --schedule="0 3 * * 0" \
  --ttl 336h \
  --snapshot-volumes=false

# Pausar schedule
velero schedule pause daily-backup

# Retomar schedule
velero schedule unpause daily-backup

# Deletar schedule
velero schedule delete meu-schedule --confirm
```

### Verificar Storage Location

```bash
velero backup-location get
```

## Troubleshooting

### Verificar Pods do Velero

```bash
kubectl get pods -n velero
kubectl logs deployment/velero -n velero
```

### Erros Comuns

#### 1. "PartiallyFailed" com erros de volume snapshots

**Causa:** MinIO não suporta snapshots nativos de EBS/AWS.

**Solução:** Use `--snapshot-volumes=false` para backups:
```bash
velero backup create meu-backup --snapshot-volumes=false
```

#### 2. Erro de conexão com MinIO

**Causa:** Pod do Velero não consegue resolver DNS interno.

**Verificar:**
```bash
kubectl exec -n velero deploy/velero -- nslookup minio.minio.svc
```

**Solução:** Verificar se o service do MinIO está rodando:
```bash
kubectl get svc -n minio
```

#### 3. Backup storage location "Unavailable"

**Causa:** Credenciais incorretas ou bucket não existe.

**Verificar:**
```bash
# Verificar bucket no MinIO
mc ls minio/velero-backups/

# Verificar secret de credenciais
kubectl get secret -n velero cloud-credentials -o yaml
```

### Verificar Conteúdo de um Backup

```bash
# Via MinIO Client (mc)
mc ls minio/velero-backups/backups/
mc ls -r minio/velero-backups/backups/meu-backup/

# Ver logs do backup
mc cat minio/velero-backups/backups/meu-backup/meu-backup-logs.gz | gunzip | head -100
```

## Backup de PersistentVolumes

O Velero usa o **node-agent** (antigo Restic) para backup de dados em PersistentVolumes.

### Habilitar Backup de PV em um Pod

Adicione a annotation ao Pod/Deployment:
```yaml
metadata:
  annotations:
    backup.velero.io/backup-volumes: "meu-volume"
```

### Exemplo de Backup com PV

```bash
# Criar backup incluindo PVs
velero backup create pv-backup \
  --include-namespaces=minha-app \
  --default-volumes-to-fs-backup \
  --wait
```

## Disaster Recovery

### Cenário: Restaurar Cluster Inteiro

1. **Instalar Velero no novo cluster** com mesma configuração de storage
2. **Verificar backup-location:**
   ```bash
   velero backup-location get
   ```
3. **Listar backups disponíveis:**
   ```bash
   velero backup get
   ```
4. **Restaurar:**
   ```bash
   velero restore create full-restore --from-backup ultimo-backup --wait
   ```

### Cenário: Migrar Namespace entre Clusters

1. **No cluster origem:**
   ```bash
   velero backup create migracao --include-namespaces=app-prod --wait
   ```

2. **No cluster destino (com mesmo storage):**
   ```bash
   velero restore create --from-backup migracao --wait
   ```

## Monitoramento

O Velero expõe métricas Prometheus na porta 8085:

```yaml
# Métricas disponíveis
velero_backup_total
velero_backup_success_total
velero_backup_failure_total
velero_backup_duration_seconds
velero_restore_total
velero_restore_success_total
```

### Alertas Sugeridos (Prometheus)

```yaml
groups:
- name: velero
  rules:
  - alert: VeleroBackupFailed
    expr: increase(velero_backup_failure_total[24h]) > 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Backup do Velero falhou"
      
  - alert: VeleroNoRecentBackup
    expr: time() - velero_backup_last_successful_timestamp > 86400
    for: 1h
    labels:
      severity: critical
    annotations:
      summary: "Nenhum backup bem-sucedido nas últimas 24h"
```

## Credenciais

As credenciais do MinIO para o Velero estão em:
- **Secret:** `cloud-credentials` no namespace `velero`
- **Arquivo local:** `/etc/velero/credentials`

### Formato do Arquivo de Credenciais

```ini
[default]
aws_access_key_id = <MINIO_USER>
aws_secret_access_key = <MINIO_PASSWORD>
```

## Referências

- [Documentação Oficial Velero](https://velero.io/docs/)
- [Velero com MinIO](https://velero.io/docs/main/contributions/minio/)
- [Backup de Persistent Volumes](https://velero.io/docs/main/file-system-backup/)
