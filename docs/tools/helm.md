# Helm — Package Manager para Kubernetes

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Kubernetes](kubernetes.md) | [Próximo: MetalLB →](metallb.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Charts instalados](#charts-instalados-pelo-raijin)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[Helm](#1-helm)¹** é o gerenciador de pacotes oficial do Kubernetes.
- Permite instalar/atualizar aplicações complexas via **[Charts](#2-chart)²** (templates YAML parametrizados).
- Versão 3+ (sem Tiller server-side).

## Por que usamos
- **Simplificação**: Instalar stack completo com um comando (`helm install`).
- **Parametrização**: Customizar via `values.yaml` sem editar templates.
- **Versionamento**: Rollback fácil para releases anteriores.
- **Repositórios**: Acesso a centenas de charts prontos (Artifact Hub).

## Como está configurado no Raijin (V1)
- **Versão**: Helm 3.14+ (latest stable)
- **Instalação**: Via script oficial do módulo `bootstrap`
- **Repositórios adicionados**:
  - `jetstack` → Cert-Manager
  - `traefik` → Traefik
  - `prometheus-community` → kube-prometheus-stack
  - `bitnami` → MinIO, Harbor (opcional)
  - `hashicorp` → Vault
  - `external-secrets` → External Secrets Operator
- **Namespace padrão**: Cada chart em namespace dedicado

## Charts instalados pelo Raijin

| Chart | Repositório | Namespace | Módulo |
|-------|-------------|-----------|--------|
| cert-manager | jetstack | cert-manager | `cert_manager` |
| traefik | traefik | traefik | `traefik` |
| kube-prometheus-stack | prometheus-community | observability | `prometheus` |
| grafana | grafana | observability | `grafana` |
| loki | grafana | observability | `loki` |
| minio | bitnami | minio | `minio` |
| harbor | harbor | harbor | `harbor` |
| vault | hashicorp | vault | `secrets` |
| external-secrets | external-secrets | external-secrets | `secrets` |
| velero | vmware-tanzu | velero | `velero` |

## Como operamos

### Comandos básicos

```bash
# Listar releases instalados
helm list -A

# Ver status de um release
helm status <release> -n <namespace>

# Ver history
helm history <release> -n <namespace>

# Desinstalar
helm uninstall <release> -n <namespace>
```

### Instalar charts

```bash
# Adicionar repositório
helm repo add bitnami https://charts.bitnami.com/bitnami

# Atualizar repos
helm repo update

# Buscar charts
helm search repo minio

# Ver valores padrão
helm show values bitnami/minio > minio-values.yaml

# Instalar com valores customizados
helm install minio bitnami/minio \
  -n minio \
  --create-namespace \
  -f minio-values.yaml
```

### Atualizar releases

```bash
# Upgrade com novos valores
helm upgrade minio bitnami/minio \
  -n minio \
  -f minio-values-new.yaml

# Upgrade para nova versão do chart
helm upgrade minio bitnami/minio \
  -n minio \
  --version 14.0.0

# Upgrade com wait
helm upgrade minio bitnami/minio \
  -n minio \
  --wait \
  --timeout 10m
```

### Rollback

```bash
# Ver revisões
helm history minio -n minio

# Rollback para revisão anterior
helm rollback minio -n minio

# Rollback para revisão específica
helm rollback minio 3 -n minio
```

## Troubleshooting

### Release em estado failed

```bash
# Ver status detalhado
helm status <release> -n <namespace>

# Ver logs de instalação
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Forçar delete e reinstalar
helm uninstall <release> -n <namespace>
kubectl delete namespace <namespace>
helm install <release> <chart> -n <namespace> --create-namespace
```

### Helm pending-install travado

```bash
# Listar secrets do Helm
kubectl get secrets -n <namespace> -l owner=helm

# Deletar secret travado
kubectl delete secret sh.helm.release.v1.<release>.v1 -n <namespace>

# Reinstalar
helm install <release> <chart> -n <namespace>
```

### Chart incompatível com versão K8s

```bash
# Ver versão suportada do chart
helm show chart bitnami/minio | grep kubeVersion

# Procurar versão antiga do chart
helm search repo bitnami/minio --versions

# Instalar versão específica
helm install minio bitnami/minio --version 12.0.0 -n minio
```

## Glossário

### 1. Helm
**Helm**: Package manager para Kubernetes; gerencia instalação e updates de aplicações complexas.
- **[helm.sh](https://helm.sh/)**

### 2. Chart
**Chart**: Pacote Helm contendo templates YAML + values + metadata (como um `.deb` ou `.rpm`).

### 3. Release
**Release**: Instância de um chart instalado no cluster (ex.: `minio` instalado com chart `bitnami/minio`).

### 4. Repository
**Repository**: Servidor HTTP que hospeda charts (ex.: Artifact Hub, Harbor).

### 5. Values
**Values**: Arquivo YAML com parâmetros de configuração do chart (`values.yaml`).

### 6. Template
**Template**: Arquivo YAML com placeholders Go Template (ex.: `{{ .Values.replicas }}`).

### 7. Rollback
**Rollback**: Reverter release para revisão anterior (preserva history).

### 8. Revision
**Revision**: Snapshot de configuração de um release (incrementa a cada upgrade).

### 9. Tiller
**Tiller**: Componente server-side do Helm 2 (removido no Helm 3).

### 10. Artifact Hub
**Artifact Hub**: Repositório público de charts (https://artifacthub.io/).

---

## Exemplos práticos

### Criar values customizado

```yaml
# minio-custom-values.yaml
mode: standalone
auth:
  rootUser: admin
  rootPassword: supersecret123
persistence:
  enabled: true
  size: 100Gi
  storageClass: local-path
resources:
  requests:
    memory: 512Mi
    cpu: 250m
  limits:
    memory: 2Gi
    cpu: 1000m
service:
  type: NodePort
  nodePorts:
    api: 30900
    console: 30901
```

```bash
helm install minio bitnami/minio \
  -n minio \
  --create-namespace \
  -f minio-custom-values.yaml
```

### Upgrade incremental

```bash
# Ver diff antes de aplicar
helm diff upgrade minio bitnami/minio \
  -n minio \
  -f minio-values-new.yaml

# Aplicar com dry-run
helm upgrade minio bitnami/minio \
  -n minio \
  -f minio-values-new.yaml \
  --dry-run

# Aplicar de verdade
helm upgrade minio bitnami/minio \
  -n minio \
  -f minio-values-new.yaml \
  --wait
```

### Template debugging

```bash
# Renderizar templates localmente
helm template minio bitnami/minio \
  -f minio-values.yaml \
  --debug > rendered.yaml

# Ver apenas um recurso específico
helm template minio bitnami/minio \
  -f minio-values.yaml \
  -s templates/deployment.yaml
```

---

## Boas práticas ✅

1. **Values versionados**: Manter `values.yaml` em Git.
2. **Dry-run antes de aplicar**: `--dry-run` para validar mudanças.
3. **Wait em upgrades**: `--wait` garante que pods ficaram prontos.
4. **Timeout adequado**: `--timeout 10m` para charts grandes.
5. **Namespaces dedicados**: Um namespace por aplicação.
6. **Pin de versões**: Especificar `--version` do chart em produção.
7. **Testar em staging**: Validar upgrades em ambiente de teste.
8. **Backup antes de upgrade**: Especialmente para stateful apps.
9. **Monitorar rollout**: `kubectl rollout status` após `helm upgrade`.
10. **Documentar customizações**: Comentar `values.yaml` com justificativas.
11. **Repositórios confiáveis**: Usar repos oficiais (Artifact Hub verificados).
12. **Limpar releases**: `helm uninstall` em vez de `kubectl delete` manual.
13. **Secrets externos**: Não colocar passwords em `values.yaml` commitado.
14. **Chart hooks**: Usar hooks para migrations/backups automáticos.
15. **Lint values**: `helm lint` para validar sintaxe.

---

## Práticas ruins ❌

1. **Senha em values commitado**: Expor credenciais no Git.
2. **Upgrade sem dry-run**: Quebrar produção sem preview.
3. **Não especificar versão**: Chart muda e quebra compatibilidade.
4. **Delete manual de recursos**: Deixa lixo; usar `helm uninstall`.
5. **Múltiplas apps no mesmo namespace**: Dificulta rollback.
6. **Não testar rollback**: Descobrir que rollback não funciona em produção.
7. **Values muito complexos**: Override de 100+ linhas dificulta manutenção.
8. **Ignorar hooks**: Migrations/cleanup não executam.
9. **Upgrade sem backup**: Perder dados em stateful apps.
10. **Repos não atualizados**: Instalar chart desatualizado.
11. **Timeout muito curto**: Helm falha antes de pods ficarem prontos.
12. **Force upgrade**: `--force` pode causar downtime desnecessário.
13. **Chart não testado**: Usar chart obscuro sem validação.
14. **Não versionar CRDs**: CRDs deletados acidentalmente em uninstall.
15. **Helm 2 em novo cluster**: Usar versão deprecada com Tiller.

---

## Diagnóstico avançado

### Ver manifests gerados

```bash
# Get manifests de release instalado
helm get manifest minio -n minio

# Salvar em arquivo
helm get manifest minio -n minio > minio-manifest.yaml
```

### Ver valores aplicados

```bash
# Values computados (padrão + custom)
helm get values minio -n minio

# Apenas valores customizados
helm get values minio -n minio --revision 1

# Ver diff entre revisões
helm diff revision minio 1 2 -n minio
```

### Debug de templates

```bash
# Renderizar com debug
helm install minio bitnami/minio \
  -f values.yaml \
  --dry-run \
  --debug

# Ver apenas hooks
helm get hooks minio -n minio
```

### Verificar repositórios

```bash
# Listar repos
helm repo list

# Atualizar todos
helm repo update

# Remover repo
helm repo remove bitnami

# Adicionar repo local
helm repo add myrepo http://charts.local.io
```

### Limpar cache

```bash
# Limpar cache de charts
rm -rf ~/.cache/helm/repository/*
helm repo update

# Limpar releases órfãos (Helm 3.7+)
helm list -A --failed
helm uninstall <release> -n <namespace>
```

### Recuperar de falha

```bash
# Se release ficou travado
helm rollback <release> -n <namespace>

# Se rollback falhar, forçar delete
kubectl delete secret -n <namespace> -l owner=helm,name=<release>

# Reinstalar do zero
helm uninstall <release> -n <namespace> --no-hooks
kubectl delete namespace <namespace>
helm install <release> <chart> -n <namespace> --create-namespace
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Kubernetes](kubernetes.md)** | **[Próximo: MetalLB →](metallb.md)**
