# Velero (Backup e Restore de Kubernetes)

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Secrets](secrets.md) | [Próximo: Harbor →](harbor.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Arquitetura](#arquitetura-resumo)
- [Operação diária](#operação-diária)
- [Schedules](#schedules)
- [Backup de PVs](#backups-de-persistentvolumes-node-agent)
- [Disaster Recovery](#disaster-recovery-rápido)
- [Monitoramento](#monitoramento-e-alertas)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos-adicionais)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- Ferramenta de **backup¹** e **restore²** para objetos Kubernetes e (opcional) volumes via **file-system backup³** (node-agent).
- No Raijin, usa MinIO **S3⁴-compatible** como backend e executa com o plugin AWS.
- Suporta **schedules⁵** (backups agendados) e restore granular por namespace/selector.

## Por que usamos
- Disaster recovery completo do cluster ou por namespace.
- Backup de **PVs⁶** (PersistentVolumes) via node-agent (file-system level).
- Migração entre clusters compartilhando bucket **S3⁴**.
- Compliance e auditoria com backups versionados.

## Como está configurado no Raijin (V1)
- Namespace: `velero`.
- Storage backend: MinIO (S3) com bucket `velero-backups`, endpoint `http://minio.minio.svc:9000`, região `minio`.
- Plugin: `velero/velero-plugin-for-aws:v1.8.0`.
- Node agent: habilitado para backups de PV (file-system backup).
- Schedule padrão: diário 02:00 UTC; retenção 7 dias (168h).
- Credenciais: usuário dedicado no MinIO com least-privilege (acesso apenas ao bucket `velero-backups`).

## O que resolve na nossa arquitetura
- Backups regulares de objetos Kubernetes (Deployments, Services, Secrets, etc.).
- Backups de PV via file-system backup (node-agent) quando anotado.
- Restore completo do cluster ou granular por namespace/selector.
- Suporte a migração entre clusters compartilhando o bucket de backups.

## Arquitetura (resumo)
```
Cluster Kubernetes
  ├─ Velero (deployment, namespace velero)
  ├─ Node Agent (DaemonSet para PVs)
  └─ MinIO (S3) -> bucket velero-backups
```

## Operação diária
- Listar backups: `velero backup get`
- Criar backup completo (sem snapshots de volume): `velero backup create meu-backup --snapshot-volumes=false --wait`
- Backup por namespace: `velero backup create ns-backup --include-namespaces=minha-app --snapshot-volumes=false --wait`
- Backup por selector: `velero backup create app-backup --selector app=minha-app --wait`
- Ver status/logs: `velero backup describe meu-backup --details` e `velero backup logs meu-backup`
- Restore completo: `velero restore create --from-backup meu-backup --wait`
- Restore de namespace: `velero restore create --from-backup meu-backup --include-namespaces=minha-app --wait`

## Schedules
- Listar: `velero schedule get`
- Criar (exemplo semanal, 3h, TTL 14 dias):
  - `velero schedule create weekly-backup --schedule="0 3 * * 0" --ttl 336h --snapshot-volumes=false`
- Pausar/retomar: `velero schedule pause <nome>` / `velero schedule unpause <nome>`

## Backups de PersistentVolumes (node-agent)
- Anotar o Pod/Deployment:
```yaml
metadata:
  annotations:
    backup.velero.io/backup-volumes: "meu-volume"
```
- Criar backup incluindo PVs: `velero backup create pv-backup --include-namespaces=minha-app --default-volumes-to-fs-backup --wait`

## Disaster Recovery rápido
1) Instalar Velero no novo cluster apontando para o mesmo backend/bucket.
2) Confirmar o backup-location: `velero backup-location get`.
3) Listar backups: `velero backup get`.
4) Restaurar: `velero restore create full-restore --from-backup <backup> --wait`.

## Monitoramento e alertas
- Métricas Prometheus na porta 8085 do deployment do Velero (scrape pelo Prometheus do cluster):
  - `velero_backup_total`, `velero_backup_success_total`, `velero_backup_failure_total`, `velero_backup_duration_seconds`, `velero_restore_total`, `velero_restore_success_total`.
- Regras sugeridas:
```yaml
- alert: VeleroBackupFailed
  expr: increase(velero_backup_failure_total[24h]) > 0
  for: 5m
  labels: { severity: warning }
  annotations:
    summary: "Backup do Velero falhou"
- alert: VeleroNoRecentBackup
  expr: time() - velero_backup_last_successful_timestamp > 86400
  for: 1h
  labels: { severity: critical }
  annotations:
    summary: "Nenhum backup bem-sucedido nas últimas 24h"
```

## Credenciais e segurança
- Secrets:
  - `cloud-credentials` (formato AWS) usado pelo Velero/Plugin AWS.
  - `minio-velero-credentials` (accesskey/secretkey) para conferência/apoio.
- Ver credenciais (exemplo):
```bash
kubectl -n velero get secret cloud-credentials -o jsonpath='{.data.cloud}' | base64 -d
kubectl -n velero get secret minio-velero-credentials -o jsonpath='{.data.accesskey}' | base64 -d
```
- Usuário MinIO com acesso somente ao bucket `velero-backups` (listar/ler/escrever; sem acesso a outros buckets).

## Troubleshooting
- Pods/logs: `kubectl get pods -n velero` e `kubectl logs deployment/velero -n velero`.
- Conectividade com MinIO: `kubectl exec -n velero deploy/velero -- nslookup minio.minio.svc`.
- Storage location Unavailable: conferir bucket via `mc ls minio/velero-backups/` e secret `cloud-credentials`.
- Erros de snapshot: usar `--snapshot-volumes=false` (MinIO não suporta snapshots nativos como EBS).
- Inspecionar backup no bucket: `mc ls -r minio/velero-backups/backups/<nome>/` e `mc cat ...-logs.gz | gunzip | head -100`.

## Referências
- https://velero.io/docs/
- https://velero.io/docs/main/contributions/minio/
- https://velero.io/docs/main/file-system-backup/

---

## Glossário

1. **Backup**: Cópia de objetos Kubernetes (Deployments, Services, Secrets, etc) e opcionalmente dados de volumes.
2. **Restore**: Recuperação de objetos/volumes a partir de um backup.
3. **File-system backup**: Backup de PVs no nível de filesystem via node-agent (DaemonSet; não usa snapshots de storage).
4. **S3** (Simple Storage Service): API de object storage da AWS; MinIO é S3-compatible.
5. **Schedule**: Backup agendado recorrente (cron expression).
6. **PV** (PersistentVolume): Volume persistente no Kubernetes.
7. **TTL** (Time To Live): Tempo de retenção do backup antes de expirar.
8. **Snapshot**: Cópia instantânea de volume (EBS, GCE Persistent Disk); MinIO não suporta.
9. **Backup Location**: Destino onde backups são armazenados (bucket S3).
10. **Node Agent**: DaemonSet que executa backups de PV via filesystem (antigo restic).

---

## Exemplos práticos adicionais

### Backup com label selector

```bash
velero backup create app-v2-backup \
  --selector app=myapp,version=v2 \
  --snapshot-volumes=false \
  --wait
```

### Restore com resource filtering

```bash
velero restore create selective-restore \
  --from-backup full-backup \
  --include-resources=deployments,services,secrets \
  --exclude-namespaces=kube-system \
  --wait
```

### Schedule com múltiplos namespaces

```bash
velero schedule create multi-ns-backup \
  --schedule="0 2 * * *" \
  --include-namespaces=apps,staging,monitoring \
  --ttl=168h \
  --snapshot-volumes=false
```

### Verificar backup no bucket MinIO

```bash
mc ls -r minio/velero-backups/backups/
mc cat minio/velero-backups/backups/my-backup/my-backup-logs.gz | gunzip | less
```

---

## Boas práticas ✅

1. **Backups diários automáticos**: Manter schedule ativo com TTL adequado (7-30 dias).
2. **Testar restores**: Validar restores periodicamente em cluster de teste.
3. **Least-privilege MinIO user**: Usuário dedicado apenas para bucket `velero-backups`.
4. **Snapshot-volumes=false no MinIO**: MinIO não suporta snapshots; sempre usar file-system backup.
5. **Anotar PVs para backup**: Adicionar annotation `backup.velero.io/backup-volumes` em pods com volumes.
6. **Backup antes de upgrades**: Criar backup manual antes de mudanças críticas.
7. **Monitorar métricas**: Configurar alertas Prometheus para backups falhados.
8. **Documentar schedules**: Manter lista de schedules ativos e seus propósitos.
9. **Verificar storage location**: Garantir que backup-location está `Available`.
10. **Retention policy**: Definir TTL para evitar crescimento ilimitado do bucket.

---

## Práticas ruins ❌

1. **Não testar restores**: Backups não testados podem estar corrompidos.
2. **Sem TTL**: Backups sem expiração esgotam storage.
3. **Credenciais em ConfigMaps**: Expor accesskey/secretkey fora de Secrets.
4. **Backups manuais apenas**: Depender de intervenção humana aumenta risco.
5. **Não monitorar falhas**: Ignorar alertas de backup falhado.
6. **Snapshot em MinIO**: Tentar usar `--snapshot-volumes=true` com MinIO (não funciona).
7. **Backup sem labels**: Dificulta restore seletivo.
8. **Não versionar manifests**: Perder histórico de configuração do Velero.
9. **Storage location único**: Não ter offsite backup (todos os backups no mesmo cluster/datacenter).
10. **Node agent sem DaemonSet**: Não habilitar node-agent quando há PVs críticos.

---

## Diagnóstico avançado

### Verificar status detalhado de backup

```bash
velero backup describe my-backup --details
velero backup logs my-backup
```

### Ver progresso de backup em andamento

```bash
watch -n 2 'velero backup get | grep InProgress'
```

### Listar backups no storage direto

```bash
kubectl exec -n velero deploy/velero -- ls /scratch
mc ls -r minio/velero-backups/backups/
```

### Verificar conectividade MinIO

```bash
kubectl exec -n velero deploy/velero -- nslookup minio.minio.svc
kubectl exec -n velero deploy/velero -- wget -O- http://minio.minio.svc:9000/minio/health/ready
```

### Logs do node-agent (PV backups)

```bash
kubectl logs -n velero -l name=node-agent --tail=100 -f
```

### Forçar re-sync de backup location

```bash
velero backup-location get
kubectl patch backuplocation default -n velero --type merge -p '{"spec":{"accessMode":"ReadWrite"}}'
```

### Ver recursos incluídos em um backup

```bash
velero backup describe my-backup --details | grep "Resource List" -A 50
```

### Validar secrets do Velero

```bash
kubectl -n velero get secret cloud-credentials -o jsonpath='{.data.cloud}' | base64 -d
kubectl -n velero get secret minio-velero-credentials -o yaml
```

### Métricas Prometheus do Velero

```bash
kubectl port-forward -n velero deploy/velero 8085:8085
curl http://localhost:8085/metrics | grep velero_backup
```

### Verificar disk usage do bucket

```bash
mc du minio/velero-backups/
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Secrets](secrets.md)** | **[Próximo: Harbor →](harbor.md)**
