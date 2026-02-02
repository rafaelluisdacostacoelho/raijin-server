# MinIO — Monitoramento, Testes e Operações

Este guia cobre todo o ciclo de vida do módulo `minio` do Raijin Server (>= 0.2.38):
provisionamento automático de StorageClass usando o NVMe local, monitoramento da
subida dos pods e validações funcionais para garantir que o armazenamento S3
compatível está pronto para produção.

## 1. Pré-requisitos e contexto

- **Cluster single-node** com taint `node-role.kubernetes.io/control-plane`. O módulo
  aplica tolerations e `nodeSelector` automaticamente.
- **Armazenamento local**: se o cluster não possuir StorageClass default, o módulo
  instala o `local-path-provisioner` e o define como padrão. Os dados ficam em
  `/opt/local-path-provisioner/` (NVMe/SSD local).
- **Credenciais root**: o CLI gera usuário/senha (`minio-admin` + secret aleatório)
  e imprime ao final da instalação. Guarde-as com segurança.

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

Execute os comandos abaixo em paralelo (tmux ou múltiplos terminais) assim que o
wizard iniciar a instalação:

| Fase | Comando | Objetivo |
| --- | --- | --- |
| StorageClass | `kubectl get storageclass` | Verificar se `local-path` está `DEFAULT` |
| PVCs | `kubectl -n minio get pvc -w` | Cada `export-minio-X` deve ir de `Pending` → `Bound` |
| Pods | `kubectl -n minio get pods -w` | Esperado: `minio-{0..3}` em `Running` + `minio-post-job` `Completed` |
| Eventos | `kubectl -n minio get events --sort-by=.metadata.creationTimestamp -w` | Diagnosticar bindings ou scheduling |
| StorageClass describe | `kubectl describe sc local-path` | Confirmar provisioner `rancher.io/local-path` |
| Logs do job | `kubectl -n minio logs job/minio-post-job -f` | Garantir criação do usuário e das políticas |

> Dica: `sudo -E ~/.venvs/midgard/bin/raijin-server debug kube --namespace minio --events 50`
> agrega pods, PVCs e eventos em um único snapshot.

## 4. Testes funcionais pós-instalação

1. **Port-forward da API S3**
   ```bash
   kubectl -n minio port-forward svc/minio 9000:9000
   # Em outro terminal
   curl -I http://localhost:9000/minio/health/ready
   ```

2. **Port-forward do Console Web (se habilitado)**
   ```bash
   kubectl -n minio port-forward svc/minio-console 9001:9001
   # Navegue até http://localhost:9001 e entre com as credenciais geradas
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

- **Status do release**: `helm status minio -n minio`
- **Uso de recursos**: `kubectl top pods -n minio`
- **Logs agregados**: `kubectl -n minio logs statefulset/minio -f`
- **Diagnóstico completo**: `sudo -E ~/.venvs/midgard/bin/raijin-server debug kube --namespace minio --events 200`
- **Administração MinIO**: `mc admin heal raijin`, `mc admin prometheus generate raijin`
- **Backups**: utilize o módulo `velero` ou scripts de snapshot do NVMe antes de upgrades.

## 6. Testes recorrentes (sanidade)

Crie um cron job (ou Github Actions) que a cada X horas:
1. Executa `mc admin info raijin` e alerta se algum nó estiver OFFLINE.
2. Realiza upload/download de um arquivo pequeno em `raijin/smoke/<timestamp>.txt`.
3. Verifica `mc du raijin` para acompanhar crescimento.

## 7. Troubleshooting rápido

| Sintoma | Ação |
| --- | --- |
| PVC em `Pending` | `kubectl describe pvc export-minio-0 -n minio`; confirme que existe StorageClass default `local-path`. Reinstale com `sudo -E ~/.venvs/midgard/bin/raijin-server minio` após `helm uninstall` e `kubectl delete pvc --all -n minio`. |
| Pod `Pending` (taint) | Certifique-se de que o node possui label `kubernetes.io/hostname=<node>`. O módulo aplica tolerations; se alterou manualmente, reexecute. |
| `minio-post-job` em BackOff | Veja logs (`kubectl -n minio logs job/minio-post-job -f`). Normalmente credenciais incorretas ou PVC não montado. |
| Console porta 9001 não responde | Confirme `consoleService` via `kubectl get svc -n minio`. Refaça o port-forward. |
| Necessário reinstalar | ```bash
helm uninstall minio -n minio
kubectl delete pvc --all -n minio
kubectl delete ns minio
sudo -E ~/.venvs/midgard/bin/raijin-server minio
``` |

## 8. Onde ficam os dados

Com o `local-path-provisioner`, cada PVC vira um diretório em
`/opt/local-path-provisioner/pvc-<uid>/`. Use `sudo du -h --max-depth=1 /opt/local-path-provisioner`
para inspecionar consumo. Para mover para outro disco, monte o NVMe desejado nesse caminho
antes de instalar o Raijin Server.

## 9. Usuários Least-Privilege

O Raijin Server cria automaticamente **usuários dedicados** para cada aplicação que usa MinIO,
seguindo o princípio de **least-privilege**:

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
# Criar alias com credenciais do vault-user
kubectl -n minio exec minio-0 -- mc alias set vault-test http://localhost:9000 vault-user '<password>'

# Tentar acessar bucket do Velero (deve falhar!)
kubectl -n minio exec minio-0 -- mc ls vault-test/velero-backups/
# Esperado: Access Denied

# Acessar bucket do Vault (deve funcionar)
kubectl -n minio exec minio-0 -- mc ls vault-test/vault-storage/
```

### Recuperar credenciais de um usuário

```bash
# Credenciais salvas no secret do namespace da aplicação
kubectl -n vault get secret minio-vault-credentials -o jsonpath='{.data.accesskey}' | base64 -d
kubectl -n vault get secret minio-vault-credentials -o jsonpath='{.data.secretkey}' | base64 -d
```
