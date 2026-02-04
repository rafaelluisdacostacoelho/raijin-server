# Segredos (Sealed-Secrets e External-Secrets)

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Observability](observability.md) | [Próximo: Velero →](velero.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Manutenção](#manutenção-e-monitoramento)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **Sealed-Secrets¹**: criptografa Secrets para armazenar em Git (controlador em `kube-system`).
- **External-Secrets²**: sincroniza segredos de backends (Vault/AWS/GCP) para Kubernetes (`external-secrets`).
- **kubeseal³**: CLI para criar SealedSecrets criptografados.

## Por que usamos
- **GitOps** seguro para segredos sensíveis (Sealed-Secrets).
- Fonte única de verdade em Vault/AWS com rotação e auditabilidade (External-Secrets).
- Elimina credenciais hardcoded e reduz vazamentos acidentais.

## Como está configurado no Raijin (V1)
- Sealed-Secrets: controlador no namespace `kube-system`; usado para armazenar segredos criptografados em Git.
- External-Secrets: operador no namespace `external-secrets`; sincroniza segredos de backends (Vault/AWS/GCP) para Secrets Kubernetes.
- Fluxo padrão: para segredos estáticos, selar e versionar; para segredos dinâmicos/rotacionados, usar ExternalSecret com `ClusterSecretStore` apontando para o backend.

## O que resolve na nossa arquitetura
- Permite GitOps seguro: arquivos versionados não expõem segredos em texto claro (Sealed-Secrets).
- Centraliza segredos em backends confiáveis (Vault/AWS/GCP) com rotação e auditabilidade, reduzindo drift entre ambiente e repositório (External-Secrets).
- Diminui risco de vazamento e de segredos expirados, com sincronização contínua.

## Como operamos
- Sealed-Secrets
  - Gerar secret: `kubectl create secret generic minha-secret --from-literal=password=123 -n default -o yaml > secret.yaml`.
  - Selar: `kubeseal --controller-namespace kube-system --controller-name sealed-secrets < secret.yaml > sealed-secret.yaml`.
  - Aplicar: `kubectl apply -f sealed-secret.yaml` (pode ir para o repo).
- External-Secrets
  - Definir `ClusterSecretStore`/`SecretStore` para o backend (ex.: Vault ou AWS Secrets Manager).
  - Criar `ExternalSecret` apontando para a chave remota; o controller gerará o Secret alvo.
  - Ver estado: `kubectl get externalsecret -A` e `kubectl describe externalsecret <nome> -n <ns>`.

## Manutenção e monitoramento
- Sealed-Secrets: monitorar `kubectl logs -n kube-system -l name=sealed-secrets-controller` para erros de decriptação; manter o par de chaves do controlador seguro (backup exigido para recuperação).
- External-Secrets: monitorar condições dos recursos `ExternalSecret` e logs do operador em `external-secrets`; validar se os Secrets alvo estão sincronizados.
- Rotação: quando backends rotacionarem segredos, External-Secrets propagará; verifique timestamps dos Secrets gerados.
- Acesso: limitar quem pode criar/alterar `ClusterSecretStore`/`SecretStore` e `ExternalSecret` via RBAC.

## Troubleshooting
- Sealed-Secrets: `kubectl logs -n kube-system -l name=sealed-secrets-controller` para ver erros de decript.
- External-Secrets: `kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets` e checar condições do recurso.
- Sempre validar se o Secret alvo foi criado/atualizado: `kubectl get secret <nome> -n <ns>`.

## Links úteis
- Sealed-Secrets: https://github.com/bitnami-labs/sealed-secrets
- External-Secrets: https://external-secrets.io/latest/

---

## Glossário

1. **Sealed-Secrets**: Solução que criptografa Secrets para versionamento seguro em Git.
2. **External-Secrets**: Operador que sincroniza segredos de backends externos para Secrets Kubernetes.
3. **kubeseal**: CLI que criptografa Secrets gerando SealedSecrets (descriptografados apenas pelo controller).
4. **RBAC** (Role-Based Access Control): Controle de acesso do Kubernetes baseado em roles/permissions.
5. **ClusterSecretStore**: Recurso global (cluster-scoped) do External-Secrets para conectar backends.
6. **SecretStore**: Versão namespace-scoped do ClusterSecretStore.
7. **ExternalSecret**: Recurso que define mapeamento entre backend externo e Secret Kubernetes.
8. **GitOps**: Prática de versionar infraestrutura/aplicações em Git como fonte de verdade.
9. **Asymmetric Encryption**: Sealed-Secrets usa par de chaves (pública/privada); apenas controller tem chave privada.
10. **Sync Interval**: Frequência de sincronização do External-Secrets com backend (padrão 1h).

---

## Exemplos práticos

### Sealed-Secrets: Fluxo completo

```bash
# 1. Criar Secret localmente (não aplicar!)
kubectl create secret generic db-credentials \
  --from-literal=username=admin \
  --from-literal=password=supersecret \
  --namespace=apps \
  --dry-run=client -o yaml > secret.yaml

# 2. Selar com kubeseal
kubeseal --controller-namespace kube-system \
  --controller-name sealed-secrets \
  --format yaml < secret.yaml > sealed-secret.yaml

# 3. Aplicar e versionar
kubectl apply -f sealed-secret.yaml
git add sealed-secret.yaml && git commit -m "Add DB credentials"
```

### External-Secrets: Vault Backend

```yaml
apiVersion: external-secrets.io/v1beta1
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
        kubernetes:
          mountPath: "kubernetes"
          role: "external-secrets"
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: app-config
  namespace: apps
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: app-config
    creationPolicy: Owner
  data:
  - secretKey: api_key
    remoteRef:
      key: myapp
      property: api_key
```

### External-Secrets: AWS Secrets Manager

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-sm
  namespace: apps
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: aws-secret
  namespace: apps
spec:
  refreshInterval: 15m
  secretStoreRef:
    name: aws-sm
    kind: SecretStore
  target:
    name: aws-credentials
  dataFrom:
  - extract:
      key: prod/myapp/credentials
```

---

## Boas práticas ✅

1. **Backup de chaves Sealed-Secrets**: Exportar e armazenar seguramente `sealed-secrets-key` do namespace `kube-system`.
2. **Rotação de segredos**: Usar External-Secrets para backends com rotação automática.
3. **RBAC restrito**: Limitar criação de ClusterSecretStore/ExternalSecret a admins.
4. **Namespace isolation**: Usar SecretStore (namespace-scoped) quando possível ao invés de ClusterSecretStore.
5. **Validar antes de commit**: Testar SealedSecret em cluster antes de versionar.
6. **Monitorar sync**: Criar alertas para ExternalSecrets com condições de erro.
7. **Refresh interval adequado**: Não usar intervalos muito curtos (aumenta load no backend).
8. **Secrets encryption at rest**: Habilitar encryption at rest do Kubernetes para camada adicional.
9. **Auditoria**: Manter logs de acesso a backends (Vault audit logs, AWS CloudTrail).
10. **Documentar mapeamentos**: Manter matriz documentando qual ExternalSecret mapeia qual backend key.

---

## Práticas ruins ❌

1. **Perder chaves Sealed-Secrets**: Sem backup, SealedSecrets ficam permanentemente inacessíveis.
2. **Secrets em plain text no Git**: Commitar `secret.yaml` antes de selar.
3. **ClusterSecretStore com credenciais hardcoded**: Expor tokens em manifests; usar ServiceAccount auth quando possível.
4. **Não monitorar ExternalSecrets**: Secrets desatualizados podem quebrar apps silenciosamente.
5. **Refresh interval muito longo**: Segredos rotacionados demoram para propagar.
6. **RBAC frouxo**: Permitir qualquer usuário criar ExternalSecrets.
7. **Sem validação**: Aplicar SealedSecrets sem testar a descriptografia.
8. **Misturar abordagens**: Usar Sealed e External-Secrets para o mesmo segredo (escolher um).
9. **Secrets órfãos**: Criar Secrets manuais que não são gerenciados por nenhum controller.
10. **Não usar scopes**: Aplicar cluster-scoped quando namespace-scoped é suficiente.

---

## Diagnóstico avançado

### Sealed-Secrets: Verificar controller

```bash
kubectl get pods -n kube-system -l name=sealed-secrets-controller
kubectl logs -n kube-system -l name=sealed-secrets-controller --tail=100 -f
```

### Sealed-Secrets: Ver chave pública

```bash
kubeseal --fetch-cert --controller-namespace kube-system --controller-name sealed-secrets
```

### Sealed-Secrets: Validar SealedSecret antes de aplicar

```bash
kubectl apply --dry-run=server -f sealed-secret.yaml
```

### Sealed-Secrets: Forçar re-criptografia (rotation)

```bash
# Exportar todas SealedSecrets
kubectl get sealedsecrets -A -o yaml > backup.yaml

# Rotate keys (gera novo par)
kubectl delete secret -n kube-system sealed-secrets-key<TAB>

# Re-selar todos com nova chave
for f in *.yaml; do
  kubeseal --re-encrypt < $f > $f.new
done
```

### External-Secrets: Ver status de sincronização

```bash
kubectl get externalsecrets -A
kubectl describe externalsecret app-config -n apps
kubectl get externalsecrets -n apps -o jsonpath='{.items[*].status.conditions[*]}'
```

### External-Secrets: Forçar refresh imediato

```bash
kubectl annotate externalsecret app-config -n apps \
  force-sync=$(date +%s) --overwrite
```

### External-Secrets: Logs do operador

```bash
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets --tail=100 -f
```

### External-Secrets: Validar conectividade com backend

```bash
# Vault
kubectl exec -n external-secrets deployment/external-secrets -- \
  wget -O- http://vault.vault.svc:8200/v1/sys/health

# AWS (via ServiceAccount)
kubectl exec -n apps -it <pod> -- \
  aws secretsmanager list-secrets --region us-east-1
```

### Comparar Secret gerado vs fonte

```bash
# Sealed-Secret
kubectl get secret db-credentials -n apps -o yaml

# External-Secret (manual check no backend)
vault kv get secret/myapp
aws secretsmanager get-secret-value --secret-id prod/myapp/credentials
```

### Verificar permissões RBAC

```bash
kubectl auth can-i create sealedsecrets --as=system:serviceaccount:apps:default -n apps
kubectl auth can-i create externalsecrets --as=system:serviceaccount:apps:default -n apps
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Observability](observability.md)** | **[Próximo: Velero →](velero.md)**
