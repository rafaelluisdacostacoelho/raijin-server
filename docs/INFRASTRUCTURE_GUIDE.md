# 🚀 Guia Completo da Infraestrutura Raijin Server

## Visão Geral

O Raijin Server provisiona uma infraestrutura Kubernetes completa e prodution-ready em Ubuntu Server, incluindo:

## Sumário rápido

- O que instalamos e como encaixa: ingress, cluster, observabilidade, segurança.
- Pré-requisitos e fluxo de deploy (mantidos abaixo).
- Guias detalhados por componente na tabela "Guias por componente".

## Escopo

Este guia descreve o fluxo padrão (V1) em hosts Ubuntu 20.04+ (bare metal ou VM) com foco em single cluster Kubernetes usando Traefik, Cert-Manager, Calico e stack de observabilidade. Casos avançados (multi-uplink, PowerEdge, NAS dedicado, IaC) serão tratados no V2.

## Guias por componente

| Componente | Guia |
|------------|------|
| Traefik (Ingress) | [docs/tools/traefik.md](docs/tools/traefik.md) |
| Cert-Manager (TLS) | [docs/tools/cert-manager.md](docs/tools/cert-manager.md) |
| Calico (CNI/NP) | [docs/tools/calico.md](docs/tools/calico.md) |
| Observabilidade (Prometheus, Grafana, Loki, Alertmanager) | [docs/tools/observability.md](docs/tools/observability.md) |
| Segredos (Sealed-Secrets, External-Secrets) | [docs/tools/secrets.md](docs/tools/secrets.md) |
| Registro de imagens | [docs/HARBOR.md](docs/HARBOR.md) |
| Armazenamento de objetos | [docs/MINIO_OPERATIONS.md](docs/MINIO_OPERATIONS.md) |
| Backup/restore | [docs/VELERO.md](docs/VELERO.md) |
| DNS interno | [docs/INTERNAL_DNS.md](docs/INTERNAL_DNS.md) |
| VPN e acesso remoto | [docs/VPN_REMOTE_ACCESS.md](docs/VPN_REMOTE_ACCESS.md) |

## Pré-requisitos (host Ubuntu)

- Ubuntu Server 20.04+ com Python 3 instalado. Se precisar instalar/atualizar:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

```
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DNS EXTERNO (A/CNAME)                       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 INGRESS + TLS  (Traefik + Cert-Manager)             │
│                    Let's Encrypt (HTTP-01)                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 REGISTRY / ARTEFATOS (Harbor)                       │
│           Imagens de app e, opcionalmente, charts Helm              │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         KUBERNETES CLUSTER                          │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │                        SUAS APLICAÇÕES                          │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│ │ Observabilidade             │  │ Rede e Segurança             │  │
│ │ Prometheus / Grafana        │  │ Calico + NetworkPolicy       │  │
│ │ Loki / Alertmanager         │  │ Sealed-Secrets                │  │
│ │                             │  │ External-Secrets -> Vault/AWS │  │
│ └─────────────────────────────┘  └──────────────────────────────┘  │
│                                                                     │
│ ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│ │ Armazenamento de Objetos    │  │ Backup / Restore             │  │
│ │ MinIO (S3 compatível)       │  │ Velero + bucket S3/MinIO     │  │
│ │ PVs para aplicações         │  │                              │  │
│ └─────────────────────────────┘  └──────────────────────────────┘  │
│                                                                     │
│ ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│ │ DNS Interno                 │  │ VPN / Acesso Remoto (WG)     │  │
│ │ CoreDNS + zonas internas    │  │ Acesso operacional seguro    │  │
│ └─────────────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Arquitetura detalhada (camadas e fluxos)

- Entrada e identidade: DNS público (A/CNAME) aponta para o endpoint publicado pelo Traefik; TLS automatizado via Cert-Manager + Let's Encrypt (HTTP-01).
- Entrega de artefatos: Harbor armazena imagens (e opcionalmente charts). Pipelines publicam aqui antes do deploy.
- Cluster Kubernetes: control plane e workers em Ubuntu 20.04+ (bare metal ou VM). Rede pod/pod e pod/service fornecida pelo Calico (BGP desabilitado por padrão).
- Segurança e segredos: Sealed-Secrets para GitOps seguro; External-Secrets para consumir segredos de Vault/AWS/GCP; NetworkPolicies default-deny nos namespaces de apps.
- Observabilidade: kube-prometheus-stack (Prometheus, Grafana, Alertmanager) + Loki para logs. Dashboards e alertas prontos para componentes core.
- Armazenamento e dados: MinIO (S3) para objetos; PVs para workloads com storage class conforme ambiente. Velero usa bucket S3/MinIO para backups de objetos Kubernetes e, se habilitado, volumes.
- Serviços de suporte: CoreDNS para zonas internas; VPN WireGuard para acesso operacional seguro (kubectl, dashboards, SSH nos nodes).

## Fluxo resumido de provisionamento (V1)

1) Hosts Ubuntu prontos (SSH, rede, storage local/NAS conforme ambiente).
2) Instalação do CLI (Python, Helm, kubectl) e bootstrap do cluster (kubeadm padrão do projeto) com Calico.
3) Instalação de ingress (Traefik) e Cert-Manager com issuers `letsencrypt-staging` e `letsencrypt-prod`.
4) Instalação de observabilidade (kube-prometheus-stack) e Loki.
5) Instalação de Harbor (registry) e, se necessário, MinIO para storage de objetos.
6) Instalação de Velero apontando para bucket S3/MinIO.
7) Instalação de Sealed-Secrets e External-Secrets + configuração de backend (Vault/AWS/GCP).
8) Configuração de CoreDNS para zonas internas e WireGuard para acesso remoto.

## Topologia de rede e nós (referência)

- Control plane: 1–3 nós com etcd embutido; IPs estáticos; porta 6443 acessível aos workers.
- Workers: IPs estáticos ou DHCP reservado; respeitam o pod CIDR do Calico e o service CIDR do cluster.
- Ingress: Service LoadBalancer ou NodePort + IP externo/keepalived/MetalLB conforme ambiente para tráfego 80/443.
- DNS interno: CoreDNS resolve serviços internos; zonas privadas adicionais são definidas conforme [docs/INTERNAL_DNS.md](docs/INTERNAL_DNS.md).
- VPN: WireGuard fornece rota para API server e serviços internos; use kubeconfig via VPN para evitar exposição pública.

## Armazenamento e backup

- Objetos: MinIO exposto via Service interno; credenciais gerenciadas via Sealed-Secrets/External-Secrets.
- Volumes persistentes: escolha da storage class por ambiente (local-path, NFS provisioner ou CSI de nuvem/bare metal); sempre defina `resources.requests.storage` em PVCs.
- Backups: Velero apontado para bucket S3/MinIO; captura objetos Kubernetes e (opcional) volumes via plugins. Agende backups regulares e teste restores em namespace isolado.

## Segurança e acesso

- TLS: Cert-Manager emite/renova automaticamente; adicionar `cert-manager.io/cluster-issuer` no Ingress.
- Rede: NetworkPolicies default-deny em namespaces de apps; liberar apenas origens necessárias (Traefik para serviços expostos, monitoramento para `/metrics`).
- Segredos: preferir External-Secrets para segredos dinâmicos (Vault/AWS/GCP); Sealed-Secrets para GitOps de segredos estáticos.
- Acesso humano: VPN WireGuard + kubeconfig controlado; evitar expor API server na internet sem restrições.
- Registro: Harbor com autenticação; use tokens/robots para CI/CD.

## Observabilidade e operação

- Dashboards: Grafana (kube-prometheus) com painéis de nodes, pods e control plane; acesso via port-forward ou VPN.
- Alertas: Alertmanager configurado; definir rotas (e-mail/webhook/chat) conforme operação.
- Logs: Loki consumido pelo Grafana; padronizar labels `namespace` e `app` nos deployments.
- Saúde rápida: `kubectl get nodes`, `kubectl get pods -A`, `kubectl top nodes/pods` (metrics-server incluso na stack).

---

## 📦 Componentes Instalados

| Componente | Função | Namespace |
|------------|--------|-----------|
| **Kubernetes** | Orquestração de containers | `kube-system` |
| **Calico** | CNI + Network Policies | `kube-system` |
| **Traefik** | Ingress Controller | `traefik` |
| **Cert-Manager** | Certificados TLS automáticos | `cert-manager` |
| **Prometheus** | Coleta de métricas | `observability` |
| **Grafana** | Dashboards e visualização | `observability` |
| **Loki** | Agregação de logs | `observability` |
| **Alertmanager** | Gerenciamento de alertas | `observability` |
| **Sealed-Secrets** | Criptografia de secrets em Git | `kube-system` |
| **External-Secrets** | Integração com Vault/AWS/GCP | `external-secrets` |

---

## 🔐 Certificados TLS (HTTPS)

### Como Funciona

1. **Cert-Manager** monitora Ingresses com a annotation `cert-manager.io/cluster-issuer`
2. Quando encontra, solicita certificado ao **Let's Encrypt**
3. Valida o domínio via HTTP-01 (Traefik responde o challenge)
4. Armazena o certificado em um Secret Kubernetes
5. **Renova automaticamente** 30 dias antes de expirar

### ClusterIssuers Disponíveis

| Nome | Uso | Certificados |
|------|-----|--------------|
| `letsencrypt-staging` | Testes | Inválidos (rate limit alto) |
| `letsencrypt-prod` | Produção | Válidos (rate limit baixo) |

### Fluxo Visual

```
[Ingress criado]
       │
       ▼
[Cert-Manager detecta annotation]
       │
       ▼
[Cria Certificate resource]
       │
       ▼
[Solicita ao Let's Encrypt]
       │
       ▼
[Let's Encrypt faz HTTP challenge]
       │
       ▼
[Traefik responde /.well-known/acme-challenge/xxx]
       │
       ▼
[Certificado emitido]
       │
       ▼
[Armazenado em Secret: <nome>-tls]
       │
       ▼
[Traefik usa o certificado]
       │
       ▼
[Renovação automática a cada ~60 dias]
```

---

## 🚀 Como Fazer Deploy de Uma Nova Aplicação

### Passo 1: Criar o Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minha-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: minha-app
  template:
    metadata:
      labels:
        app: minha-app
    spec:
      containers:
        - name: minha-app
          image: minha-imagem:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

### Passo 2: Criar o Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: minha-app
  namespace: default
spec:
  selector:
    app: minha-app
  ports:
    - port: 80
      targetPort: 8080
```

### Passo 3: Criar o Ingress (com TLS automático)

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: minha-app
  namespace: default
  annotations:
    # ⬇️ ISSO É TUDO QUE VOCÊ PRECISA PARA TLS AUTOMÁTICO
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - minha-app.meudominio.com
      secretName: minha-app-tls  # Cert-manager cria automaticamente
  rules:
    - host: minha-app.meudominio.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: minha-app
                port:
                  number: 80
```

### Passo 4: Aplicar

```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

### Passo 5: Verificar Certificado

```bash
# Ver status do certificado
kubectl get certificate -n default

# Detalhes (se houver erro)
kubectl describe certificate minha-app-tls -n default

# Ver eventos do cert-manager
kubectl get events -n cert-manager --sort-by='.lastTimestamp'
```

---

## 📊 Observabilidade

### Acessar Grafana

```bash
# Port-forward local
kubectl port-forward svc/grafana 3000:80 -n observability

# Acessar em: http://localhost:3000
# Usuário: admin
# Senha: (definida na instalação ou em secret)
```

### Acessar Prometheus

```bash
kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n observability
# Acessar em: http://localhost:9090
```

### Ver Logs com Loki

No Grafana, use o datasource **Loki** e queries como:

```logql
# Logs de uma aplicação específica
{namespace="default", app="minha-app"}

# Logs com erro
{namespace="default"} |= "error"

# Logs dos últimos 5 minutos
{namespace="default"} | json | level="error"
```

---

## 🛡️ Segurança

### Network Policies (Calico)

Por padrão, o Calico aplica **default-deny** no namespace `default`. Para permitir tráfego:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: minha-app
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: traefik  # Permite tráfego do Traefik
      ports:
        - port: 8080
```

### Secrets Seguros

**Opção 1: Sealed Secrets (GitOps)**

```bash
# Criar secret criptografado
kubeseal --controller-namespace kube-system \
  --controller-name sealed-secrets \
  < secret.yaml > sealed-secret.yaml

# Aplicar (pode commitar no Git!)
kubectl apply -f sealed-secret.yaml
```

**Opção 2: External Secrets (Vault/AWS)**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: minha-secret
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: minha-secret
  data:
    - secretKey: password
      remoteRef:
        key: secret/data/myapp
        property: password
```

---

## 🔧 Comandos Úteis

### Kubernetes

```bash
# Ver todos os pods
kubectl get pods -A

# Ver logs de um pod
kubectl logs -f <pod-name> -n <namespace>

# Entrar em um pod
kubectl exec -it <pod-name> -n <namespace> -- /bin/sh

# Ver recursos do cluster
kubectl top nodes
kubectl top pods -A
```

### Cert-Manager

```bash
# Ver certificados
kubectl get certificates -A

# Ver ClusterIssuers
kubectl get clusterissuers

# Debug de certificado
kubectl describe certificate <nome> -n <namespace>

# Ver challenges pendentes
kubectl get challenges -A

# Diagnóstico completo
raijin-server cert diagnose
```

### Helm

```bash
# Ver releases instalados
helm list -A

# Ver valores de um release
helm get values <release> -n <namespace>

# Atualizar release
helm upgrade <release> <chart> -n <namespace> -f values.yaml
```

---

## 🔄 Fluxo de Deploy Típico

```
1. Desenvolver aplicação
       │
       ▼
2. Criar imagem Docker
   docker build -t minha-app:v1 .
   docker push registry/minha-app:v1
       │
       ▼
3. Criar manifests Kubernetes
   - deployment.yaml
   - service.yaml
   - ingress.yaml (com annotation cert-manager)
       │
       ▼
4. Aplicar no cluster
   kubectl apply -f .
       │
       ▼
5. Verificar
   kubectl get pods
   kubectl get certificate
       │
       ▼
6. Acessar via HTTPS
   https://minha-app.meudominio.com ✅
```

---

## ❓ Troubleshooting

### Certificado não é emitido

```bash
# 1. Ver status do certificate
kubectl describe certificate <nome> -n <namespace>

# 2. Ver challenges
kubectl get challenges -A
kubectl describe challenge <nome> -n <namespace>

# 3. Ver logs do cert-manager
kubectl logs -n cert-manager -l app.kubernetes.io/component=controller

# 4. Verificar se DNS aponta para o cluster
nslookup minha-app.meudominio.com
```

### Pod não inicia

```bash
# Ver eventos
kubectl describe pod <nome> -n <namespace>

# Ver logs
kubectl logs <nome> -n <namespace> --previous
```

### Ingress não funciona

```bash
# Verificar Traefik
kubectl get pods -n traefik
kubectl logs -n traefik -l app.kubernetes.io/name=traefik

# Verificar Ingress
kubectl describe ingress <nome> -n <namespace>
```

---

## 📁 Estrutura de Namespaces

```
kube-system          # Componentes core do Kubernetes + Calico + Sealed-Secrets
cert-manager         # Cert-manager e seus componentes
traefik              # Ingress Controller
observability        # Prometheus, Grafana, Loki, Alertmanager
external-secrets     # External Secrets Operator
default              # Suas aplicações (ou crie namespaces específicos)
```

---

## 🎯 Checklist para Nova Aplicação

- [ ] Imagem Docker publicada em registry acessível
- [ ] Deployment com resources (requests/limits) definidos
- [ ] Service apontando para as portas corretas
- [ ] Ingress com:
  - [ ] `ingressClassName: traefik`
  - [ ] `cert-manager.io/cluster-issuer: "letsencrypt-prod"`
  - [ ] TLS configurado com `secretName`
  - [ ] Host configurado no DNS apontando para o cluster
- [ ] NetworkPolicy permitindo tráfego (se default-deny ativo)
- [ ] Secrets usando Sealed-Secrets ou External-Secrets

---

## 📚 Referências

- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Cert-Manager Docs](https://cert-manager.io/docs/)
- [Traefik Docs](https://doc.traefik.io/traefik/)
- [Prometheus Operator](https://prometheus-operator.dev/)
- [Grafana Docs](https://grafana.com/docs/)
