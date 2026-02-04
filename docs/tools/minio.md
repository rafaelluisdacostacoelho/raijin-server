# MinIO — S3-Compatible Object Storage

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Harbor](harbor.md) | [Próximo: Vault →](vault.md)

---

## Índice
- [Pré-requisitos](#1-pré-requisitos-e-contexto)
- [Instalação](#2-fluxo-rápido-de-instalação)
- [Monitoramento](#3-monitoramento-da-subida)
- [Testes funcionais](#4-testes-funcionais-pós-instalação)
- [Operação](#5-operação-e-observabilidade-contínua)
- [Testes recorrentes](#6-testes-recorrentes-sanidade)
- [Troubleshooting](#7-troubleshooting-rápido)
- [Armazenamento](#8-onde-ficam-os-dados)
- [Least-Privilege](#9-usuários-least-privilege)
- [Glossário](#glossário)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

Este guia cobre todo o ciclo de vida do módulo `minio` do Raijin Server (>= 0.2.38): provisionamento automático de **[StorageClass](#2-storageclass)²** usando o NVMe local, monitoramento da subida dos pods e validações funcionais para garantir que o armazenamento **[S3](#1-s3)¹ compatível** está pronto para produção.

## 1. Pré-requisitos e contexto

- **Cluster single-node** com taint `node-role.kubernetes.io/control-plane`. O módulo aplica tolerations e `nodeSelector` automaticamente.
- **Armazenamento local**: se o cluster não possuir StorageClass default, o módulo instala o `local-path-provisioner` e o define como padrão. Os dados ficam em `/opt/local-path-provisioner/` (NVMe/SSD local).
- **Credenciais root**: o CLI gera usuário/senha (`minio-admin` + secret aleatório) e imprime ao final da instalação. Guarde-as com segurança.
- **Least-Privilege³**: usuários dedicados por aplicação com acesso restrito a buckets específicos.

## 2. Fluxo rápido de instalação

```bash
source ~/.venvs/midgard/bin/activate
pip install -U raijin-server==0.2.38
sudo -E ~/.venvs/midgard/bin/raijin-server minio
```

Durante o wizard:
1. O módulo detecta/instala a StorageClass (`local-path`).
2. Escolha `standalone` ou `distributed` (4 pods) e defina requests/limits.
3. Informe o tamanho dos PVCs (ex.: `50Gi`).
4. Confirme se deseja habilitar o Console Web.

## 3. Monitoramento da subida

Execute os comandos abaixo em paralelo assim que o wizard iniciar a instalação:

| Fase | Comando | Objetivo |
| --- | --- | --- |
| StorageClass | `kubectl get storageclass` | Verificar se `local-path` está `DEFAULT` |
| PVCs | `kubectl -n minio get pvc -w` | Cada `export-minio-X` deve ir de `Pending` → `Bound` |
| Pods | `kubectl -n minio get pods -w` | Esperado: `minio-{0..3}` em `Running` + `minio-post-job` `Completed` |
| Eventos | `kubectl -n minio get events --sort-by=.metadata.creationTimestamp -w` | Diagnosticar bindings ou scheduling |
| StorageClass describe | `kubectl describe sc local-path` | Confirmar provisioner `rancher.io/local-path` |
| Logs do job | `kubectl -n minio logs job/minio-post-job -f` | Garantir criação do usuário e das políticas |

## 4. Testes funcionais pós-instalação

1. **Port-forward da API S3**
   ```bash
   kubectl -n minio port-forward svc/minio 9000:9000
   curl -I http://localhost:9000/minio/health/ready
   ```

2. **Port-forward do Console Web (se habilitado)**
   ```bash
   kubectl -n minio port-forward svc/minio-console 9001:9001
   # Acesse http://localhost:9001 com as credenciais geradas
   ```

3. **Validar via MinIO Client (mc)**
   ```bash
   export MINIO_ROOT_USER="<root_user>"
   export MINIO_ROOT_PASSWORD="<root_password>"
   mc alias set raijin http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
   mc admin info raijin
   mc mb raijin/test-bucket
   mc cp /etc/hosts raijin/test-bucket/hosts.txt
   mc ls raijin/test-bucket
   ```

4. **Health-checks nativos**
   ```bash
   curl -s http://localhost:9000/minio/health/live
   curl -s http://localhost:9000/minio/health/cluster
   ```

## 5. Operação e observabilidade contínua

- Status do release: `helm status minio -n minio`
- Uso de recursos: `kubectl top pods -n minio`
- Logs agregados: `kubectl -n minio logs statefulset/minio -f`
- Diagnóstico completo: `sudo -E ~/.venvs/midgard/bin/raijin-server debug kube --namespace minio --events 200`
- Administração MinIO: `mc admin heal raijin`, `mc admin prometheus generate raijin`
- Backups: use o módulo `velero` ou snapshots do NVMe antes de upgrades.

## 6. Testes recorrentes (sanidade)

- Rodar periodicamente (cron/CI):
  1. `mc admin info raijin` e alertar se algum nó estiver OFFLINE.
  2. Upload/download de arquivo pequeno em `raijin/smoke/<timestamp>.txt`.
  3. `mc du raijin` para acompanhar crescimento.

## 7. Troubleshooting rápido

| Sintoma | Ação |
| --- | --- |
| PVC em `Pending` | `kubectl describe pvc export-minio-0 -n minio`; confirme StorageClass default `local-path`. Se necessário, reinstalar (`helm uninstall minio -n minio` + apagar PVCs/ns) e rodar o módulo novamente. |
| Pod `Pending` (taint) | Verificar label do node `kubernetes.io/hostname=<node>`; o módulo aplica tolerations. |
| `minio-post-job` em BackOff | Logs: `kubectl -n minio logs job/minio-post-job -f` (geralmente credenciais ou PVC). |
| Console 9001 não responde | Conferir `kubectl get svc -n minio`; refazer port-forward. |
| Necessário reinstalar | `helm uninstall minio -n minio && kubectl delete pvc --all -n minio && kubectl delete ns minio && sudo -E ~/.venvs/midgard/bin/raijin-server minio`. |

## 8. Onde ficam os dados

Com `local-path-provisioner`, cada PVC vira um diretório em `/opt/local-path-provisioner/pvc-<uid>/`. Use `sudo du -h --max-depth=1 /opt/local-path-provisioner` para ver consumo. Se quiser usar outro disco, monte o NVMe desejado nesse caminho antes de instalar.

## 9. Usuários Least-Privilege

O Raijin cria usuários dedicados por aplicação no MinIO (princípio de least-privilege):

| Aplicação | Usuário MinIO | Bucket(s) | Criado pelo módulo |
|-----------|---------------|-----------|-------------------|
| Vault | `vault-user` | `vault-storage` | `secrets` |
| Velero | `velero-user` | `velero-backups` | `velero` |
| Harbor | `harbor-user` | `harbor-registry`, `harbor-chartmuseum`, `harbor-jobservice` | `harbor` |
| Loki | `loki-user` | `loki-chunks` | `loki` |

### Verificar usuários existentes

```bash
kubectl -n minio exec minio-0 -- mc admin user ls local
```

### Verificar políticas

```bash
kubectl -n minio exec minio-0 -- mc admin policy ls local
kubectl -n minio exec minio-0 -- mc admin policy info local vault-policy
```

### Testar isolamento

```bash
kubectl -n minio exec minio-0 -- mc alias set vault-test http://localhost:9000 vault-user '<password>'
# Deve falhar acessar bucket de outro app
kubectl -n minio exec minio-0 -- mc ls vault-test/velero-backups/
# Deve funcionar no bucket do Vault
kubectl -n minio exec minio-0 -- mc ls vault-test/vault-storage/
```

### Recuperar credenciais de um usuário

```bash
kubectl -n vault get secret minio-vault-credentials -o jsonpath='{.data.accesskey}' | base64 -d
kubectl -n vault get secret minio-vault-credentials -o jsonpath='{.data.secretkey}' | base64 -d
```

---

## Glossário

1. **S3** (Simple Storage Service): API de object storage da AWS; MinIO implementa compatibilidade total.
2. **StorageClass**: Recurso Kubernetes que define como provisionar PVs (local-path, AWS EBS, etc).
3. **Least-Privilege**: Princípio de segurança onde cada usuário/app tem apenas as permissões mínimas necessárias.
4. **PVC** (PersistentVolumeClaim): Requisição de armazenamento persistente no Kubernetes.
5. **Bucket**: Container lógico no S3/MinIO para armazenar objetos (similar a diretório).
6. **Object**: Arquivo armazenado no S3/MinIO (até 5TB por objeto).
7. **Access Key / Secret Key**: Credenciais de autenticação no S3/MinIO (similar a username/password).
8. **Policy**: Regra JSON que define permissões (read, write, list) para buckets/objetos.
9. **Standalone Mode**: MinIO rodando em 1 pod (single-node; sem HA).
10. **Distributed Mode**: MinIO com 4+ pods para alta disponibilidade e erasure coding.
11. **Erasure Coding**: Técnica de redundância que divide objetos em chunks com paridade (similar a RAID).
12. **mc** (MinIO Client): CLI para gerenciar MinIO (equivalente ao `aws s3` CLI).
13. **Console**: UI web do MinIO para administração (porta 9001).
14. **API Port**: Porta S3-compatible do MinIO (9000 padrão).
15. **Health Endpoints**: `/minio/health/live`, `/minio/health/ready`, `/minio/health/cluster`.

---

## Boas práticas ✅

1. **Least-privilege users**: Criar usuário dedicado por aplicação com acesso apenas aos buckets necessários.
2. **Backup de credenciais root**: Armazenar credenciais admin em Vault ou gerenciador de secrets.
3. **Distributed mode em produção**: Usar 4+ pods para HA (evita single point of failure).
4. **PVC sizing adequado**: Planejar crescimento; redimensionar PVC é complexo.
5. **StorageClass com retention**: Usar `reclaimPolicy: Retain` para evitar perda acidental de dados.
6. **Monitoramento Prometheus**: Habilitar endpoint `/minio/v2/metrics/cluster` e configurar scraping.
7. **Backups periódicos**: Usar `mc mirror` ou Velero para backup de buckets críticos.
8. **Policies versionadas**: Versionar arquivos JSON de policies em Git.
9. **Audit logs**: Habilitar audit logging do MinIO para rastreabilidade.
10. **TLS interno**: Em produção, usar TLS entre pods do MinIO (distributed mode).
11. **Quotas por bucket**: Configurar quotas para prevenir uso excessivo.
12. **Lifecycle policies**: Configurar expiração automática de objetos antigos quando aplicável.
13. **Separação física**: Em multi-node, usar discos dedicados por node para melhor performance.
14. **Health checks**: Configurar readiness/liveness probes adequadamente.
15. **Documentar users**: Manter matriz de usuários → aplicações → buckets → policies.

---

## Práticas ruins ❌

1. **Credenciais root em CI/CD**: Usar admin user em pipelines; criar robot users dedicados.
2. **Sem backup de PVCs**: Perder dados por falha de disco sem backup externo.
3. **Single-pod em produção**: Standalone mode sem HA cria single point of failure.
4. **Policies permissivas**: Dar `s3:*` quando apenas `s3:GetObject` é necessário.
5. **Buckets compartilhados**: Múltiplas apps no mesmo bucket dificulta least-privilege.
6. **Sem monitoramento**: Não coletar métricas de uso/performance.
7. **PVC subdimensionado**: Storage insuficiente causa crash dos pods.
8. **Não testar restores**: Backups sem validação podem estar corrompidos.
9. **Credenciais hardcoded**: Expor access/secret keys em código ou manifests.
10. **Sem versionamento**: Não habilitar versioning em buckets críticos.
11. **Lifecycle policies agressivas**: Deletar objetos críticos por políticas mal configuradas.
12. **Não usar mc admin heal**: Em distributed mode, não rodar heal após falhas de disco.
13. **Console exposto publicamente**: Expor porta 9001 sem autenticação adicional.
14. **PVC em storage lento**: Usar HDD para workloads latency-sensitive.
15. **Ignorar health checks**: Não configurar probes adequados causa indisponibilidade não detectada.

---

## Diagnóstico avançado

### Ver status completo do cluster MinIO

```bash
kubectl -n minio exec minio-0 -- mc admin info local
```

### Verificar disk usage por bucket

```bash
kubectl -n minio exec minio-0 -- mc du local/
kubectl -n minio exec minio-0 -- mc du local/harbor-registry/ --depth 2
```

### Listar todos os buckets

```bash
kubectl -n minio exec minio-0 -- mc ls local/
```

### Listar usuários e policies

```bash
kubectl -n minio exec minio-0 -- mc admin user ls local
kubectl -n minio exec minio-0 -- mc admin policy ls local
```

### Ver policy específica

```bash
kubectl -n minio exec minio-0 -- mc admin policy info local vault-policy
```

### Verificar health via API

```bash
kubectl port-forward -n minio svc/minio 9000:9000
curl http://localhost:9000/minio/health/live
curl http://localhost:9000/minio/health/ready
curl http://localhost:9000/minio/health/cluster
```

### Métricas Prometheus

```bash
kubectl port-forward -n minio svc/minio 9000:9000
curl http://localhost:9000/minio/v2/metrics/cluster | grep minio_
```

### Testar performance com mc

```bash
kubectl -n minio exec minio-0 -- mc support perf object local/test-bucket --size 10MB --duration 30s
```

### Verificar PVC binding

```bash
kubectl get pvc -n minio
kubectl describe pvc export-minio-0 -n minio
```

### Ver logs de todos os pods

```bash
kubectl logs -n minio statefulset/minio --tail=100 -f
```

### Verificar uso de disco no host

```bash
sudo du -h --max-depth=1 /opt/local-path-provisioner/
df -h | grep local-path
```

### Testar conectividade S3 de outro pod

```bash
kubectl run -it --rm debug --image=alpine --restart=Never -- sh
apk add curl
curl -I http://minio.minio.svc:9000/minio/health/ready
```

### Heal distributed cluster (após falha de disco)

```bash
kubectl -n minio exec minio-0 -- mc admin heal local/ --recursive
```

### Exportar configuração do MinIO

```bash
kubectl -n minio exec minio-0 -- mc admin config export local > minio-config.json
```

### Verificar versionamento de bucket

```bash
kubectl -n minio exec minio-0 -- mc version info local/my-bucket
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Harbor](harbor.md)** | **[Próximo: Vault →](vault.md)**
