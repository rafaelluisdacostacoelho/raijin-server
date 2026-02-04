# HashiCorp Vault + External Secrets Operator

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: MinIO](minio.md)

---

## Índice
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Configuração Inicial](#configuração-inicial)
- [Gerenciamento de Segredos](#gerenciamento-de-segredos)
- [Integração com Kubernetes](#integração-com-kubernetes)
- [Backup e Restore](#backup-e-restore)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Boas e Más Práticas](#boas-e-más-práticas)
- [Referências](#referências)

---

## Arquitetura

```
Kubernetes Cluster
  ├─ Vault Pod (UI:30820, API:8200) → MinIO bucket vault-storage
  ├─ External Secrets Operator (sincroniza Vault → K8s Secrets)
  ├─ ClusterSecretStore vault-backend
  └─ Aplicações consumindo Secrets nativos do K8s (transparent)
```

Fluxo de sincronização:
1. Admin cria segredo no **Vault¹** (via UI/CLI).
2. **ExternalSecret³** mapeia path do Vault → Secret K8s.
3. **ESO²** sincroniza periodicamente (default 1h).
4. Aplicações usam Secret nativo (transparente).

Benefícios: apps não conhecem o Vault; secrets centralizados/auditáveis; sincronização automática; backup via MinIO.

---

## Instalação (via raijin-server)

```bash
raijin-server install secrets
```
Prompts típicos:
- Namespace Vault: `vault`
- Namespace ESO: `external-secrets`
- MinIO host: `minio.minio.svc:9000` ou NodePort
- Usuário MinIO dedicado: `vault-user` (least-privilege) + secret gerado

Instalações automáticas:
- Vault (chart hashicorp/vault), storage MinIO bucket `vault-storage`, UI NodePort 30820, API 8200.
- External Secrets Operator (CRDs ClusterSecretStore/SecretStore/ExternalSecret).
- KV v2 em `secret/` habilitado; ClusterSecretStore `vault-backend` criado.
- Secrets: `vault-init-credentials` (root token + unseal key), `minio-vault-credentials` (access/secret key).

---

## Configuração Inicial

- Root token e unseal keys:
```bash
kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d
kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.unseal-key}' | base64 -d
```
Guarde em local seguro.

- UI via VPN: http://192.168.1.100:30820 (login com root token).

- Unseal manual após reboot:
```bash
kubectl -n vault exec vault-0 -- vault status
kubectl -n vault exec vault-0 -- vault operator unseal <key1>
kubectl -n vault exec vault-0 -- vault operator unseal <key2>
kubectl -n vault exec vault-0 -- vault operator unseal <key3>
```

---

## Gerenciamento de Segredos

- Dentro do pod (usando root token do secret):
```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$(kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d) vault kv put secret/myapp username=admin password=secret123
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$(kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d) vault kv get secret/myapp
```

- Via port-forward:
```bash
kubectl -n vault port-forward svc/vault 8200:8200
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d)
vault kv put secret/myapp username=admin password=secret123
```

---

## Integração com Kubernetes (ESO)

ClusterSecretStore já criado:
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

Exemplo de ExternalSecret:
```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: myapp-external-secret
  namespace: default
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: myapp-credentials
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
```

---

## Backup e Restore

- Dados persistem no bucket `vault-storage` (MinIO). Use o módulo Velero para backup do namespace `vault` e do bucket.
- Exporte o secret `vault-init-credentials` e guarde externamente (root token/unseal key).

---

## Troubleshooting

- Pods/logs: `kubectl get pods -n vault` e `kubectl logs -n vault sts/vault`.
- ESO logs: `kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets`.
- Status Vault: `kubectl -n vault exec vault-0 -- vault status`.
- DNS/MinIO: `kubectl -n vault exec vault-0 -- nslookup minio.minio.svc`.

---

## Referências
- https://www.vaultproject.io/docs
- https://external-secrets.io/

---

## Glossário

1. **Vault**: Sistema de gerenciamento de secrets da HashiCorp com criptografia, auditoria e controle de acesso.
2. **External Secrets Operator** (ESO): Operador Kubernetes que sincroniza secrets de backends externos (Vault/AWS/GCP) para Secrets nativos.
3. **ExternalSecret**: Recurso CRD que define mapeamento entre path no backend e Secret Kubernetes.
4. **KV Store** (Key-Value Store): Engine do Vault para armazenar secrets simples (v1: sem versioning; v2: com versioning).
5. **Unseal**: Processo de descriptografar o Vault após reboot usando unseal keys (Shamir secret sharing).
6. **Token**: Credencial de autenticação no Vault (root token: acesso total; service tokens: escopos limitados).
7. **Secret Engine**: Plugin do Vault para diferentes tipos de secrets (KV, database credentials, PKI, etc).
8. **Policy**: Regra HCL que define permissões (read, write, delete) para paths do Vault.
9. **Seal/Unseal**: Estado do Vault (sealed: criptografado, inacessível; unsealed: operacional).
10. **ClusterSecretStore**: Recurso ESO global (cluster-scoped) que conecta backend (Vault/AWS).
11. **Audit Log**: Registro completo de todas as operações no Vault (leitura, escrita, autenticação).
12. **Shamir Secret Sharing**: Algoritmo que divide unseal key em N partes (threshold: M de N necessários para unseal).
13. **Auto-unseal**: Configuração avançada onde Vault usa HSM/Cloud KMS para unseal automático (não usado no Raijin V1).
14. **Refresh Interval**: Frequência de sincronização do ExternalSecret com Vault (default 1h).
15. **Namespace** (Vault): Isolamento multi-tenancy no Vault Enterprise (não usado no OSS).

---

## Boas práticas ✅

1. **Backup de unseal keys**: Armazenar as 3+ unseal keys em locais seguros separados (cofre, gerenciador de passwords).
2. **Root token apenas para setup**: Criar service tokens com policies específicas para operações.
3. **Policies least-privilege**: Criar policy por aplicação com acesso apenas aos paths necessários.
4. **Audit logs habilitados**: Manter logs de auditoria para compliance e troubleshooting.
5. **Versioning KV v2**: Usar secret engine KV v2 para histórico de mudanças.
6. **Refresh interval adequado**: Não usar intervalos muito curtos (aumenta load no Vault).
7. **ExternalSecret por namespace**: Separar ExternalSecrets por namespace da aplicação.
8. **Backup do bucket vault-storage**: Incluir no Velero ou fazer snapshot do MinIO.
9. **HA setup em produção**: Rodar múltiplas réplicas do Vault com Raft/Consul backend (V2).
10. **TLS interno**: Em produção, usar TLS entre Vault e ESO.
11. **Monitorar sealed state**: Alertar se Vault ficar sealed após reboot.
12. **Documentar paths**: Manter matriz de paths → aplicações → policies.
13. **Rotação de secrets**: Usar dynamic secrets engines quando possível (DB credentials, AWS IAM).
14. **Limitar root token**: Revogar root token após setup inicial e gerar novo apenas quando necessário.
15. **Teste de unseal**: Validar procedimento de unseal em ambiente de teste.

---

## Práticas ruins ❌

1. **Perder unseal keys**: Sem as keys, Vault fica permanentemente inacessível.
2. **Root token em ExternalSecret**: Usar root token no ClusterSecretStore expõe acesso total.
3. **KV v1 para secrets críticos**: Sem versioning, não há rollback de mudanças acidentais.
4. **Policies permissivas**: Dar `path "secret/*" { capabilities = ["create", "read", "update", "delete"] }` quando apenas `read` é necessário.
5. **Não monitorar sealed state**: Vault sealed silenciosamente impede sincronização do ESO.
6. **Refresh interval muito longo**: Secrets rotacionados demoram para propagar (default 1h pode ser muito).
7. **Sem audit logs**: Perder rastreabilidade de quem acessou/modificou secrets.
8. **Credenciais hardcoded**: Expor root token em manifests ou CI/CD.
9. **Não testar restores**: Backup do bucket sem validação.
10. **Single-pod sem HA**: Em produção, single point of failure.
11. **Não versionar policies**: Perder histórico de mudanças em permissões.
12. **Ignorar logs do ESO**: Não monitorar erros de sincronização.
13. **ClusterSecretStore com credenciais expostas**: Token no manifest ao invés de ServiceAccount auth.
14. **Não usar namespaces K8s**: Misturar ExternalSecrets de apps diferentes no mesmo namespace.
15. **Auto-unseal sem HSM**: Tentar auto-unseal sem infraestrutura adequada (cloud KMS/HSM).

---

## Diagnóstico avançado

### Verificar status do Vault

```bash
kubectl -n vault exec vault-0 -- vault status
kubectl get pods -n vault
kubectl logs -n vault sts/vault --tail=100 -f
```

### Unseal manual após reboot

```bash
# Pegar unseal keys do secret
kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.unseal-key}' | base64 -d

# Executar unseal (repetir até threshold)
kubectl -n vault exec vault-0 -- vault operator unseal <key1>
kubectl -n vault exec vault-0 -- vault operator unseal <key2>
kubectl -n vault exec vault-0 -- vault operator unseal <key3>
```

### Listar secrets no KV

```bash
export VAULT_TOKEN=$(kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d)
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault kv list secret/
```

### Ver versões de um secret (KV v2)

```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault kv metadata get secret/myapp
```

### Restaurar versão anterior

```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault kv rollback -version=2 secret/myapp
```

### Verificar policies

```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault policy list
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault policy read myapp-policy
```

### Ver audit logs

```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault audit list
kubectl logs -n vault vault-0 | grep audit
```

### Verificar ExternalSecrets

```bash
kubectl get externalsecrets -A
kubectl describe externalsecret myapp-external-secret -n apps
kubectl get externalsecrets -n apps -o jsonpath='{.items[*].status.conditions[*]}'
```

### Logs do ESO

```bash
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets --tail=100 -f
```

### Forçar refresh imediato de ExternalSecret

```bash
kubectl annotate externalsecret myapp-external-secret -n apps \
  force-sync=$(date +%s) --overwrite
```

### Verificar conectividade Vault ↔ MinIO

```bash
kubectl -n vault exec vault-0 -- nslookup minio.minio.svc
kubectl -n vault exec vault-0 -- wget -O- http://minio.minio.svc:9000/minio/health/ready
```

### Testar leitura via port-forward

```bash
kubectl port-forward -n vault svc/vault 8200:8200
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(kubectl -n vault get secret vault-init-credentials -o jsonpath='{.data.root-token}' | base64 -d)
vault kv get secret/myapp
```

### Ver usage de storage no bucket

```bash
mc du minio/vault-storage/
mc ls -r minio/vault-storage/ | head -20
```

### Criar service token com policy específica

```bash
# Criar policy
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN vault policy write myapp-policy - <<EOF
path "secret/data/myapp/*" {
  capabilities = ["read"]
}
EOF

# Gerar token
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN \
  vault token create -policy=myapp-policy -period=768h
```

### Revogar token

```bash
kubectl -n vault exec vault-0 -- env VAULT_TOKEN=$VAULT_TOKEN \
  vault token revoke <token-to-revoke>
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: MinIO](minio.md)**
