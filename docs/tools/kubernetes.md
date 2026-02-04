# Kubernetes Core

> **Navegação**: [← Voltar ao Índice](README.md) | [Próximo: Helm →](helm.md)

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
- **[Kubernetes](#1-kubernetes)¹** (K8s) é uma plataforma open-source para orquestração de containers.
- Instalado via **[kubeadm](#2-kubeadm)²** (ferramenta oficial) com **[containerd](#3-containerd)³** como runtime.
- Control plane e worker unificados em **[single-node](#4-single-node)⁴** (V1).

## Por que usamos
- Orquestração declarativa de workloads via **[manifests YAML](#5-manifest)⁵**.
- Self-healing, auto-scaling e rolling updates nativos.
- Ecossistema maduro com ampla adoção (CNCF).
- Base para toda infraestrutura Raijin (ingress, storage, monitoring).

## Como está configurado no Raijin (V1)
- **Versão**: Kubernetes 1.28+ (latest stable via apt)
- **Runtime**: containerd (cgroup v2, systemd driver)
- **Network Plugin**: Calico (instalado separadamente)
- **Control Plane**: Single-node com taint removido para permitir workloads
- **Pod Network CIDR**: 10.244.0.0/16 (padrão Calico)
- **Service CIDR**: 10.96.0.0/12 (padrão kubeadm)
- **Kubeconfig**: `/etc/kubernetes/admin.conf` (copiado para `~/.kube/config`)
- **CNI**: Calico (NetworkPolicy habilitado)
- **Storage**: local-path-provisioner (instalado pelo módulo MinIO)

## O que o Kubernetes resolve na nossa arquitetura
- **Orquestração**: Gerencia ciclo de vida de containers (Deployments, StatefulSets, DaemonSets).
- **Rede**: Service discovery e load balancing interno (ClusterIP, NodePort, LoadBalancer).
- **Armazenamento**: Abstração de volumes persistentes (PV/PVC).
- **Configuração**: ConfigMaps e Secrets para injetar configurações.
- **Observabilidade**: Logs, métricas e events nativos.
- **Segurança**: RBAC, NetworkPolicies, PodSecurityPolicies.

## Como operamos

### Comandos básicos

```bash
# Ver nodes
kubectl get nodes

# Ver todos os pods
kubectl get pods -A

# Ver recursos de um namespace
kubectl get all -n <namespace>

# Descrever recurso
kubectl describe pod <pod-name> -n <namespace>

# Logs
kubectl logs <pod-name> -n <namespace> -f

# Executar comando em pod
kubectl exec -it <pod-name> -n <namespace> -- bash

# Port-forward
kubectl port-forward -n <namespace> svc/<service> 8080:80
```

### Gerenciamento de recursos

```bash
# Aplicar manifest
kubectl apply -f manifest.yaml

# Deletar recurso
kubectl delete -f manifest.yaml
kubectl delete pod <pod-name> -n <namespace>

# Editar recurso
kubectl edit deployment <name> -n <namespace>

# Scale
kubectl scale deployment <name> --replicas=3 -n <namespace>

# Restart
kubectl rollout restart deployment/<name> -n <namespace>
```

## Manutenção e monitoramento

### Health checks

```bash
# Status do cluster
kubectl cluster-info
kubectl get componentstatuses

# Status dos nodes
kubectl get nodes
kubectl describe node <node-name>

# Eventos recentes
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

# Uso de recursos
kubectl top nodes
kubectl top pods -A
```

### Verificações periódicas

```bash
# Certificados (expiram em 1 ano)
sudo kubeadm certs check-expiration

# Pods não rodando
kubectl get pods -A | grep -v Running

# PVCs pendentes
kubectl get pvc -A | grep Pending

# Nodes NotReady
kubectl get nodes | grep NotReady
```

### Renovação de certificados

```bash
# Renovar todos os certificados
sudo kubeadm certs renew all

# Verificar expiração
sudo kubeadm certs check-expiration

# Reiniciar control plane
sudo systemctl restart kubelet
```

## Troubleshooting

### Pod não inicia

```bash
# Ver status detalhado
kubectl describe pod <pod-name> -n <namespace>

# Ver eventos
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Ver logs (mesmo se crashou)
kubectl logs <pod-name> -n <namespace> --previous

# Verificar recursos
kubectl top pod <pod-name> -n <namespace>
```

### Node NotReady

```bash
# Descrever node
kubectl describe node <node-name>

# Verificar kubelet
sudo systemctl status kubelet
sudo journalctl -u kubelet -f

# Verificar containerd
sudo systemctl status containerd
sudo journalctl -u containerd -f

# Reiniciar kubelet
sudo systemctl restart kubelet
```

### Rede não funciona

```bash
# Verificar Calico
kubectl get pods -n kube-system -l k8s-app=calico-node

# DNS interno
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl exec -it <pod> -n <namespace> -- nslookup kubernetes.default

# Testar conectividade pod-to-pod
kubectl run -it --rm debug --image=busybox --restart=Never -- ping <pod-ip>
```

## Glossário

### 1. Kubernetes
**Kubernetes** (K8s): Plataforma de orquestração de containers open-source originalmente desenvolvida pelo Google.
- **[Documentação oficial](https://kubernetes.io/docs/)**

### 2. kubeadm
**kubeadm**: Ferramenta oficial para bootstrap de clusters Kubernetes (setup do control plane).
- **[Guia kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/)**

### 3. containerd
**containerd**: Runtime de containers (substituto do Docker, compatível com CRI).
- **[containerd.io](https://containerd.io/)**

### 4. Single-node
**Single-node**: Cluster com control plane e workers no mesmo node (não recomendado para produção multi-tenant).

### 5. Manifest
**Manifest**: Arquivo YAML declarativo que define recursos Kubernetes (Pods, Services, Deployments).

### 6. Control Plane
**Control Plane**: Componentes que gerenciam o cluster (API Server, etcd, Scheduler, Controller Manager).

### 7. Worker Node
**Worker Node**: Node que executa workloads (pods); em single-node, o control plane também atua como worker.

### 8. Pod
**Pod**: Menor unidade deployável; um ou mais containers compartilhando rede e storage.

### 9. Deployment
**Deployment**: Recurso que gerencia ReplicaSets e rolling updates de Pods.

### 10. Service
**Service**: Abstração de rede que expõe Pods (ClusterIP, NodePort, LoadBalancer).

### 11. Namespace
**Namespace**: Isolamento lógico de recursos dentro do cluster.

### 12. PV/PVC
**PersistentVolume/PersistentVolumeClaim**: Abstração de armazenamento persistente.

### 13. RBAC
**RBAC** (Role-Based Access Control): Sistema de permissões do Kubernetes.
- **[RBAC Docs](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)**

### 14. CNI
**CNI** (Container Network Interface): Plugin de rede (Calico, Flannel, etc).

### 15. CRI
**CRI** (Container Runtime Interface): Interface para runtimes (containerd, CRI-O).

---

## Exemplos práticos

### Deployment básico

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.25
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "128Mi"
            cpu: "500m"
```

### Service ClusterIP

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx
  namespace: default
spec:
  type: ClusterIP
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
```

### ConfigMap e Secret

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: default
data:
  app.conf: |
    server {
      listen 80;
      server_name example.com;
    }
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secret
  namespace: default
type: Opaque
stringData:
  password: supersecret123
```

### Job e CronJob

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: backup-job
spec:
  template:
    spec:
      containers:
      - name: backup
        image: alpine
        command: ["sh", "-c", "echo backup completed"]
      restartPolicy: Never
  backoffLimit: 3
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: alpine
            command: ["sh", "-c", "date; echo backup"]
          restartPolicy: OnFailure
```

---

## Boas práticas ✅

1. **Namespaces por ambiente**: Separar apps, staging, monitoring em namespaces distintos.
2. **Resource limits**: Sempre definir requests/limits para CPU e memória.
3. **Readiness/Liveness probes**: Configurar health checks em todos os Pods.
4. **Labels consistentes**: Usar labels padronizados (`app`, `env`, `version`).
5. **RBAC granular**: Criar ServiceAccounts e Roles específicos (não usar default).
6. **Secrets externos**: Usar External-Secrets ao invés de hardcode.
7. **Backup do etcd**: Fazer backup periódico do etcd (onde ficam todos os dados do cluster).
8. **Renovar certificados**: Monitorar expiração (`kubeadm certs check-expiration`).
9. **Monitorar uso de recursos**: Configurar alertas para CPU/memória altos.
10. **NetworkPolicies**: Habilitar default-deny e liberar apenas o necessário.
11. **Versionar manifests**: Manter todos os YAML em Git.
12. **Imagens com tag específica**: Evitar `:latest` em produção.
13. **Logs estruturados**: Emitir logs em JSON para melhor parseamento.
14. **Affinity/Anti-affinity**: Em multi-node, distribuir pods críticos.
15. **PodDisruptionBudgets**: Proteger apps críticos durante rolling updates.

---

## Práticas ruins ❌

1. **Pods sem limits**: Pode causar OOM e afetar outros workloads.
2. **Usar `latest` tag**: Dificulta rollback e reprodutibilidade.
3. **Secrets em ConfigMaps**: Expor credenciais em texto claro.
4. **Rodar como root**: Containers devem usar usuário não-privilegiado.
5. **Não configurar probes**: Pods crashados não são detectados rapidamente.
6. **Namespaces misturados**: TST e PRD no mesmo namespace.
7. **RBAC permissivo**: Dar `cluster-admin` desnecessariamente.
8. **Não monitorar etcd**: Perder dados por falta de backup.
9. **Certificados expirados**: Cluster para de funcionar abruptamente.
10. **Não testar manifests**: `kubectl apply` direto em produção sem dry-run.
11. **HostPath volumes**: Quebra portabilidade entre nodes.
12. **Logs não centralizados**: Dificulta troubleshooting.
13. **Pods sem requests**: Scheduler não consegue otimizar placement.
14. **Não versionar CRDs**: Atualizações de Operators podem quebrar.
15. **Ignorar events**: Perder sinais de problemas (FailedScheduling, etc).

---

## Diagnóstico avançado

### Backup do etcd

```bash
# Backup manual
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /backup/etcd-snapshot-$(date +%Y%m%d-%H%M%S).db

# Verificar snapshot
sudo ETCDCTL_API=3 etcdctl snapshot status /backup/etcd-snapshot-*.db --write-out=table
```

### Restore do etcd

```bash
# Parar API server
sudo mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/

# Restore
sudo ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd-snapshot.db \
  --data-dir=/var/lib/etcd-restore

# Atualizar configuração do etcd
sudo vim /etc/kubernetes/manifests/etcd.yaml
# Alterar data-dir para /var/lib/etcd-restore

# Reiniciar
sudo mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/
```

### Debug de rede

```bash
# Verificar rotas
kubectl get nodes -o jsonpath='{.items[*].spec.podCIDR}'
ip route

# Verificar iptables (Calico usa)
sudo iptables -t nat -L -n -v | grep <pod-ip>

# DNS debug
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- bash
nslookup kubernetes.default
dig kubernetes.default.svc.cluster.local
```

### Logs do control plane

```bash
# API Server
sudo journalctl -u kubelet | grep apiserver

# Scheduler
kubectl logs -n kube-system kube-scheduler-<node>

# Controller Manager
kubectl logs -n kube-system kube-controller-manager-<node>

# etcd
kubectl logs -n kube-system etcd-<node>
```

### Verificar certificados

```bash
# Listar certificados
sudo kubeadm certs check-expiration

# Verificar CA
sudo openssl x509 -in /etc/kubernetes/pki/ca.crt -text -noout | grep -A2 Validity

# Verificar API server cert
sudo openssl x509 -in /etc/kubernetes/pki/apiserver.crt -text -noout | grep -A2 Validity
```

### Performance tuning

```bash
# Ver uso de recursos dos pods
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory

# Ver eventos de eviction
kubectl get events -A | grep Evicted

# Ver pods em OOMKilled
kubectl get pods -A -o json | jq '.items[] | select(.status.containerStatuses[]?.lastState.terminated.reason=="OOMKilled") | {name:.metadata.name, namespace:.metadata.namespace}'
```

---

**[← Voltar ao Índice](README.md)** | **[Próximo: Helm →](helm.md)**
