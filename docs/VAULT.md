# HashiCorp Vault + External Secrets Operator

Guia completo de instalação, configuração e uso do Vault integrado ao Kubernetes com External Secrets Operator.

## Índice

- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Configuração Inicial](#configuração-inicial)
- [Gerenciamento de Segredos](#gerenciamento-de-segredos)
- [Integração com Kubernetes](#integração-com-kubernetes)
- [Backup e Restore](#backup-e-restore)
- [Troubleshooting](#troubleshooting)
- [Referências](#referências)

---

## Arquitetura

### Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                    │
│                                                              │
│  ┌──────────────┐         ┌─────────────────────────────┐  │
│  │   Vault Pod  │         │ External Secrets Operator   │  │
│  │              │◄────────│                             │  │
│  │  - UI:30820  │  Auth   │  - Sincroniza secrets       │  │
│  │  - API:8200  │         │    do Vault → K8s Secrets   │  │
│  └──────┬───────┘         └─────────────┬───────────────┘  │
│         │                               │                   │
│         │ Storage Backend               │ Cria/Atualiza     │
│         ▼                               ▼                   │
│  ┌──────────────┐         ┌──────────────────────────┐     │
│  │    MinIO     │         │     Kubernetes Secrets    │     │
│  │ (vault-      │         │  (secrets nativos do K8s) │     │
│  │  storage)    │         └──────────────────────────┘     │
│  └──────────────┘                      │                    │
│                                        │                    │
│                                        ▼                    │
│                            ┌──────────────────────┐         │
│                            │   Aplicações (Pods)  │         │
│                            │   Usam Secrets       │         │
│                            │   transparentemente  │         │
│                            └──────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Sincronização

1. **Administrador**: Cria segredo no Vault via CLI/UI
2. **ExternalSecret**: Define mapeamento Vault → K8s Secret
3. **ESO Operator**: Sincroniza automaticamente (polling 15min-1h)
4. **Aplicação**: Consome Secret nativo do Kubernetes

**Benefícios**:
- ✅ Aplicações não precisam conhecer Vault (usam Secrets padrão)
- ✅ Secrets centralizados e auditados no Vault
- ✅ Sincronização automática de mudanças
- ✅ Backup persistido no MinIO

---

## Instalação

### Pré-requisitos

- Kubernetes cluster funcionando
- MinIO instalado com bucket `vault-storage`
- Helm 3.x instalado
- Acesso via VPN (para UI do Vault)

### Instalação via raijin-server

```bash
raijin-server install secrets
```

**Prompts durante instalação**:
- `Namespace para Vault`: `vault` (padrão)
- `Namespace para External Secrets`: `external-secrets` (padrão)
- `MinIO host`: `minio.minio.svc:9000` (interno) ou `192.168.1.81:30900` (NodePort)
- `MinIO Access Key`: `vault-user` (criado automaticamente com least-privilege)
- `MinIO Secret Key`: (gerado automaticamente)

### O que é instalado

1. **HashiCorp Vault**
   - Chart: `hashicorp/vault`
   - Namespace: `vault`
   - Storage: MinIO S3-compatible (`vault-storage` bucket)
   - UI: NodePort 30820
   - API: ClusterIP 8200

2. **External Secrets Operator**
   - Chart: `external-secrets/external-secrets`
   - Namespace: `external-secrets`
   - CRDs: ClusterSecretStore, SecretStore, ExternalSecret

3. **Configurações automáticas**
   - Vault inicializado e unsealed
   - KV v2 engine habilitado em `secret/`
   - ClusterSecretStore `vault-backend` criado
   - Credenciais salvas em secret `vault-init-credentials` no namespace vault

4. **MinIO Least-Privilege**
   - Usuário `vault-user` criado com acesso **apenas** ao bucket `vault-storage`
   - Policy S3 restritiva aplicada automaticamente
   - Credenciais salvas em secret `minio-vault-credentials` no namespace vault

---

## Configuração Inicial

### Unseal Keys e Root Token

**IMPORTANTE**: Após instalação, keys são salvas em:

**Arquivo local** (se usado `--save-keys`):
```
/etc/vault/keys.json
```

**Secret Kubernetes** (sempre):
```bash
# Root Token
kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d

# Unseal Key
kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.unseal-key}' | base64 -d
```

⚠️ **BACKUP OBRIGATÓRIO**: Guarde essas keys em local seguro (cofre físico, gerenciador de senhas, etc.)

### Acesso ao Vault UI

1. **Via VPN**:
   ```
   http://192.168.1.81:30820
   ```

2. **Fazer login**:
   - Method: Token
   - Token: (copiar de `/etc/vault/keys.json`)

3. **Navegar**:
   - Secrets → `secret/` → Ver/Criar secrets
   - Access → Policies → Ver policies
   - Access → Auth Methods → Ver métodos de autenticação

### Unseal Manual (após reboot)

Se o Vault pod reiniciar, ele ficará "sealed":

```bash
# Ver status
kubectl -n vault exec vault-0 -- vault status

# Unseal (precisa de 3 keys das 5)
kubectl -n vault exec vault-0 -- vault operator unseal <key1>
kubectl -n vault exec vault-0 -- vault operator unseal <key2>
kubectl -n vault exec vault-0 -- vault operator unseal <key3>
```

**Script helper** (usar keys de /etc/vault/keys.json):
```bash
#!/bin/bash
KEYS=$(jq -r '.unseal_keys_b64[]' /etc/vault/keys.json)
I=0
for KEY in $KEYS; do
    kubectl -n vault exec vault-0 -- vault operator unseal $KEY
    I=$((I+1))
    if [ $I -eq 3 ]; then break; fi
done
echo "Vault unsealed!"
```

---

## Gerenciamento de Segredos

### CLI - Dentro do Pod

```bash
# Alias útil
alias vault-exec="kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$(jq -r .root_token /etc/vault/keys.json) vault"

# Criar segredo
vault-exec kv put secret/myapp \
    username=admin \
    password=secret123 \
    api_key=abc-xyz-789

# Ler segredo
vault-exec kv get secret/myapp

# Atualizar campo específico
vault-exec kv patch secret/myapp password=newsecret456

# Listar secrets
vault-exec kv list secret/

# Ver histórico de versões
vault-exec kv metadata get secret/myapp

# Deletar versão específica
vault-exec kv delete -versions=2 secret/myapp

# Deletar completamente (metadata + versões)
vault-exec kv metadata delete secret/myapp
```

### CLI - Via Port-Forward

```bash
# Terminal 1: Port-forward
kubectl -n vault port-forward svc/vault 8200:8200

# Terminal 2: Usar CLI local
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(jq -r .root_token /etc/vault/keys.json)

vault kv put secret/myapp username=admin password=secret123
vault kv get secret/myapp
```

### UI - Via Browser

1. Acessar: http://192.168.1.81:30820
2. Login com root token
3. Navegar: Secrets → `secret/` → Create secret
4. Preencher:
   - Path: `myapp`
   - Secret data:
     ```
     username = admin
     password = secret123
     api_key = abc-xyz-789
     ```
5. Save

---

## Integração com Kubernetes

### Conceitos

- **ClusterSecretStore**: Configuração global para acessar Vault (todos os namespaces)
- **SecretStore**: Configuração por namespace
- **ExternalSecret**: Define quais secrets sincronizar do Vault → K8s

### ClusterSecretStore (já criado)

```yaml
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.vault.svc:8200"
      path: "secret"
      version: "v2"
      auth:
        tokenSecretRef:
          namespace: vault
          name: vault-init-credentials
          key: root-token
```

> **Nota**: Em produção, recomenda-se usar Kubernetes Auth ao invés de token estático.

### Exemplo 1: Sincronizar Secret Individual

**1. Criar segredo no Vault**:
```bash
kubectl -n vault exec vault-0 -- \
    env VAULT_TOKEN=<root-token> \
    vault kv put secret/myapp \
    username=admin \
    password=supersecret123 \
    db_host=postgres.example.com
```

**2. Criar ExternalSecret**:
```yaml
# myapp-secret.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: myapp-external-secret
  namespace: default
spec:
  refreshInterval: 1h  # Sincroniza a cada 1 hora
  
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  
  target:
    name: myapp-credentials  # Nome do Secret K8s
    creationPolicy: Owner
  
  data:
  - secretKey: username
    remoteRef:
      key: secret/myapp
      property: username
  
  - secretKey: password
    remoteRef:
      key: secret/myapp
      property: password
  
  - secretKey: db_host
    remoteRef:
      key: secret/myapp
      property: db_host
```

**3. Aplicar**:
```bash
kubectl apply -f myapp-secret.yaml
```

**4. Verificar sincronização**:
```bash
# Ver ExternalSecret status
kubectl -n default get externalsecret myapp-external-secret
# NAME                      STORE           REFRESH   STATUS
# myapp-external-secret     vault-backend   1h        SecretSynced

# Ver Secret criado
kubectl -n default get secret myapp-credentials -o yaml
```

**5. Usar no Pod**:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  containers:
  - name: app
    image: nginx
    env:
    - name: USERNAME
      valueFrom:
        secretKeyRef:
          name: myapp-credentials
          key: username
    - name: PASSWORD
      valueFrom:
        secretKeyRef:
          name: myapp-credentials
          key: password
```

### Exemplo 2: Sincronizar Todas as Chaves

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: database-credentials
  namespace: default
spec:
  refreshInterval: 30m
  
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  
  target:
    name: database-credentials
    creationPolicy: Owner
  
  dataFrom:
  # Sincroniza TODAS as chaves de secret/database
  - extract:
      key: secret/database
```

### Exemplo 3: Template Customizado

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: app-config
  namespace: default
spec:
  refreshInterval: 1h
  
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  
  target:
    name: app-config
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        # Template de arquivo de configuração
        config.yaml: |
          database:
            host: {{ .db_host }}
            port: {{ .db_port }}
            username: {{ .db_user }}
            password: {{ .db_password }}
          
          api:
            key: {{ .api_key }}
            secret: {{ .api_secret }}
  
  data:
  - secretKey: db_host
    remoteRef:
      key: secret/production/database
      property: host
  - secretKey: db_port
    remoteRef:
      key: secret/production/database
      property: port
  - secretKey: db_user
    remoteRef:
      key: secret/production/database
      property: username
  - secretKey: db_password
    remoteRef:
      key: secret/production/database
      property: password
  - secretKey: api_key
    remoteRef:
      key: secret/production/api
      property: key
  - secretKey: api_secret
    remoteRef:
      key: secret/production/api
      property: secret
```

### Verificar Status de Sincronização

```bash
# Ver todos ExternalSecrets
kubectl get externalsecret -A

# Ver detalhes de um específico
kubectl -n default describe externalsecret myapp-external-secret

# Ver logs do ESO
kubectl -n external-secrets logs deployment/external-secrets -f

# Forçar sincronização imediata (anotar ExternalSecret)
kubectl -n default annotate externalsecret myapp-external-secret \
    force-sync=$(date +%s)
```

---

## Backup e Restore

### Storage Backend

Vault usa MinIO bucket `vault-storage`. O Velero já faz backup desse bucket diariamente.

### Backup Manual de Secrets

**Exportar todos secrets**:
```bash
#!/bin/bash
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=$(jq -r .root_token /etc/vault/keys.json)

# Port-forward
kubectl -n vault port-forward svc/vault 8200:8200 &
sleep 5

# Exportar
vault kv list -format=json secret/ | jq -r '.[]' | while read path; do
    echo "Backing up secret/$path"
    vault kv get -format=json secret/$path > backup-$(echo $path | tr '/' '-').json
done

# Cleanup
kill %1
```

### Restore de Secrets

```bash
#!/bin/bash
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=$(jq -r .root_token /etc/vault/keys.json)

# Port-forward
kubectl -n vault port-forward svc/vault 8200:8200 &
sleep 5

# Restaurar
for file in backup-*.json; do
    path=$(echo $file | sed 's/backup-//; s/\.json//; s/-/\//g')
    echo "Restoring secret/$path"
    
    # Extrair data do JSON e criar comando vault kv put
    data=$(jq -r '.data.data | to_entries | map("\(.key)=\(.value)") | join(" ")' $file)
    vault kv put secret/$path $data
done

# Cleanup
kill %1
```

### Restore Completo (Disaster Recovery)

Se perder completamente o cluster:

1. **Reinstalar Vault**:
   ```bash
   raijin-server install secrets
   ```

2. **Recuperar unseal keys antigas** (do backup de /etc/vault/keys.json)

3. **Unseal com keys antigas**

4. **Dados persistem no MinIO** (bucket vault-storage)

5. **Recriar ClusterSecretStore e ExternalSecrets**

---

## Troubleshooting

### Vault Sealed após Reboot

**Sintoma**: Pod vault-0 Running mas status "Sealed"

```bash
kubectl -n vault exec vault-0 -- vault status
# Sealed: true
```

**Solução**: Unseal manualmente
```bash
# Pegar keys de /etc/vault/keys.json
kubectl -n vault exec vault-0 -- vault operator unseal <key1>
kubectl -n vault exec vault-0 -- vault operator unseal <key2>
kubectl -n vault exec vault-0 -- vault operator unseal <key3>
```

### ExternalSecret não sincroniza

**Sintoma**: ExternalSecret status "SecretSyncedError"

```bash
kubectl -n default describe externalsecret myapp-secret
# Events:
#   Warning  SecretSyncedError  secret not found: secret/myapp
```

**Solução**: Verificar se secret existe no Vault
```bash
kubectl -n vault exec vault-0 -- \
    env VAULT_TOKEN=<token> \
    vault kv get secret/myapp
```

### ESO não tem permissão

**Sintoma**: Erro "permission denied" nos logs

```bash
kubectl -n external-secrets logs deployment/external-secrets | grep denied
```

**Solução**: Verificar policy e role
```bash
# Ver policy
kubectl -n vault exec vault-0 -- \
    env VAULT_TOKEN=<token> \
    vault policy read eso-policy

# Ver role
kubectl -n vault exec vault-0 -- \
    env VAULT_TOKEN=<token> \
    vault read auth/kubernetes/role/eso-role
```

### UI não acessível

**Sintoma**: http://192.168.1.81:30820 timeout

**Solução**:
```bash
# Verificar pod
kubectl -n vault get pods

# Verificar service
kubectl -n vault get svc vault
# Deve ter type: NodePort e nodePort: 30820

# Verificar se porta está aberta
sudo ss -tlnp | grep 30820

# Testar acesso local no servidor
curl http://192.168.1.81:30820/ui/
```

### MinIO connection refused

**Sintoma**: Pod vault-0 CrashLoopBackOff, logs mostram erro S3

```bash
kubectl -n vault logs vault-0 | grep -i error
# Error: connection refused to minio
```

**Solução**: Verificar MinIO
```bash
# MinIO está rodando?
kubectl -n minio get pods

# NodePort acessível?
curl http://192.168.1.81:30900/minio/health/live

# Bucket existe?
mc ls minio/vault-storage
```

### Secret não atualiza em tempo real

**Sintoma**: Mudou secret no Vault mas K8s Secret não atualizou

**Explicação**: ExternalSecret sincroniza via polling (15min-1h)

**Solução**: Forçar sincronização imediata
```bash
kubectl -n default annotate externalsecret myapp-secret \
    force-sync=$(date +%s)
```

### Comandos Úteis

```bash
# Ver status geral
kubectl -n vault get pods,svc
kubectl -n external-secrets get pods
kubectl get clustersecretstore
kubectl get externalsecret -A

# Logs
kubectl -n vault logs vault-0
kubectl -n external-secrets logs deployment/external-secrets -f

# Deletar e recriar ExternalSecret
kubectl -n default delete externalsecret myapp-secret
kubectl -n default apply -f myapp-secret.yaml

# Testar conectividade Vault
kubectl run -it --rm debug --image=alpine --restart=Never -- sh
apk add curl
curl http://vault.vault.svc.cluster.local:8200/v1/sys/health
```

---

## Referências

### Documentação Oficial

- **Vault**: https://www.vaultproject.io/docs
- **Vault API**: https://www.vaultproject.io/api-docs
- **External Secrets**: https://external-secrets.io/latest/
- **ESO Vault Provider**: https://external-secrets.io/latest/provider/hashicorp-vault/

### Comandos Vault Úteis

```bash
# Autenticação
vault login <token>

# KV v2 commands
vault kv put secret/path key=value
vault kv get secret/path
vault kv patch secret/path key=newvalue
vault kv delete -versions=1 secret/path
vault kv metadata delete secret/path

# Policies
vault policy list
vault policy read policy-name
vault policy write policy-name policy.hcl

# Auth methods
vault auth list
vault auth enable kubernetes
vault write auth/kubernetes/config

# Secrets engines
vault secrets list
vault secrets enable -path=secret kv-v2

# Status
vault status
vault operator unseal
```

### Exemplos YAML

Todos os exemplos estão em:
```
examples/secrets/
├── clustersecretstore-vault-kubernetes.yaml
├── externalsecret-myapp.yaml
└── README.md
```

### Checklist de Produção

- [ ] Root token armazenado em local seguro (não usar em produção)
- [ ] Unseal keys em cofre físico/gerenciador de senhas
- [ ] Criar tokens com TTL limitado para aplicações
- [ ] Configurar policies granulares por namespace/app
- [ ] Habilitar audit logs: `vault audit enable file file_path=/vault/logs/audit.log`
- [ ] Backup regular do bucket MinIO vault-storage
- [ ] Monitorar métricas Vault (Prometheus integration)
- [ ] Configurar auto-unseal (AWS KMS, GCP KMS) em produção
- [ ] Testar disaster recovery completo
- [ ] Documentar processo de unseal para equipe on-call

---

**Instalado via**: `raijin-server install secrets` (módulo secrets.py)

**Suporte**: Verificar logs do ESO e Vault para troubleshooting detalhado.
