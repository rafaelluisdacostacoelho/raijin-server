# 🚀 Guia Completo da Infraestrutura Raijin Server

## Visão Geral

O Raijin Server provisiona uma infraestrutura Kubernetes completa e prodution-ready em Ubuntu Server, incluindo:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INTERNET                                    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INGRESS LAYER                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐    │
│  │   Traefik   │    │ Cert-Manager │    │    Let's Encrypt    │    │
│  │  (Ingress)  │◄───│  (TLS Auto)  │◄───│   (Certificados)    │    │
│  └─────────────┘    └──────────────┘    └─────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     KUBERNETES CLUSTER                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    SUAS APLICAÇÕES                           │   │
│  │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │   │
│  │   │  App 1  │  │  App 2  │  │  App 3  │  │  App N  │        │   │
│  │   └─────────┘  └─────────┘  └─────────┘  └─────────┘        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    OBSERVABILIDADE                           │   │
│  │   ┌───────────┐  ┌─────────┐  ┌──────┐  ┌──────────────┐    │   │
│  │   │Prometheus │  │ Grafana │  │ Loki │  │ Alertmanager │    │   │
│  │   │ (Métricas)│  │(Dashb.) │  │(Logs)│  │  (Alertas)   │    │   │
│  │   └───────────┘  └─────────┘  └──────┘  └──────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      SEGURANÇA                               │   │
│  │   ┌────────┐  ┌────────────────┐  ┌───────────────────┐     │   │
│  │   │ Calico │  │ Sealed-Secrets │  │ External-Secrets  │     │   │
│  │   │ (CNI)  │  │  (Criptografia)│  │ (Vault/AWS/GCP)   │     │   │
│  │   └────────┘  └────────────────┘  └───────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

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
