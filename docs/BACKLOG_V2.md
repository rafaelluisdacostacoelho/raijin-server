# Raijin Server v2.0.0 - Backlog Técnico

## 📋 Visão Geral

Este documento descreve as funcionalidades planejadas para a versão 2.0.0 do Raijin Server,
focada em **arquitetura multi-node**, **integração enterprise** e **alta disponibilidade**.

---

## 🎯 Objetivos da v2.0.0

1. **Multi-Node Cluster**: Suporte a workers adicionais (bare-metal, VMs, Dell PowerEdge)
2. **Enterprise Storage**: Integração nativa com NAS (Synology, TrueNAS, QNAP)
3. **Multi-WAN**: Suporte a múltiplos links de internet com failover e load balancing
4. **High Availability**: Control plane HA com múltiplos masters
5. **Edge Computing**: Suporte a nodes remotos via VPN

---

## 🔧 Módulos Planejados

### 1. `worker.py` - Gerenciamento de Workers

**Propósito**: Adicionar, remover e gerenciar worker nodes no cluster.

**Comandos CLI**:
```bash
raijin worker add <hostname> [--ip IP] [--role worker|storage]
raijin worker remove <hostname> [--drain] [--force]
raijin worker list [--status]
raijin worker prepare <hostname>  # Prepara node remoto via SSH
raijin worker join-command        # Gera comando kubeadm join
```

**Funcionalidades**:
- [ ] Geração de token kubeadm com TTL configurável
- [ ] Preparação remota de workers via SSH/Ansible
- [ ] Detecção automática de recursos (CPU, RAM, GPU)
- [ ] Labels automáticos baseado em hardware
- [ ] Drain seguro antes de remoção
- [ ] Suporte a taints para workloads específicos

**Variáveis de Ambiente**:
```bash
RAIJIN_WORKER_SSH_USER=raijin
RAIJIN_WORKER_SSH_KEY=/path/to/key
RAIJIN_WORKER_ROLES=worker,storage
RAIJIN_WORKER_LABELS=zone=datacenter1
```

**Dependências**:
- kubernetes (control plane inicializado)
- calico (CNI configurado)
- metallb (opcional, para LoadBalancer)

---

### 2. `cluster.py` - Gerenciamento de Cluster Multi-Node

**Propósito**: Operações de cluster como upgrade, backup do etcd, health checks.

**Comandos CLI**:
```bash
raijin cluster status               # Status geral do cluster
raijin cluster health               # Health check detalhado
raijin cluster upgrade [--version]  # Upgrade do Kubernetes
raijin cluster backup               # Backup do etcd
raijin cluster restore <snapshot>   # Restore do etcd
raijin cluster certificates         # Gerencia certificados
```

**Funcionalidades**:
- [ ] Upgrade rolling de Kubernetes (control plane + workers)
- [ ] Backup automatizado do etcd (CronJob)
- [ ] Restore point-in-time do etcd
- [ ] Renovação automática de certificados
- [ ] Métricas de saúde do cluster
- [ ] Detecção de nodes problemáticos

---

### 3. `storage.py` - Integração com Storage Enterprise

**Propósito**: Configurar storage distribuído para clusters multi-node.

**Comandos CLI**:
```bash
raijin storage setup <type>         # longhorn|nfs|ceph|local
raijin storage nas add <ip>         # Adiciona NAS como backend
raijin storage status               # Status dos PVs/PVCs
raijin storage benchmark            # Benchmark de I/O
```

**Suporte a NAS**:
- [ ] **Synology**: NFS, iSCSI, SMB
- [ ] **TrueNAS**: NFS v4.1, iSCSI
- [ ] **QNAP**: NFS, iSCSI
- [ ] **Opções OpenSource**: OpenEBS, Rook-Ceph

**Storage Classes**:
```yaml
# StorageClass para NAS
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nas-ssd
provisioner: nfs.csi.k8s.io
parameters:
  server: nas.local
  share: /volume1/k8s
  mountPermissions: "0777"
reclaimPolicy: Retain
volumeBindingMode: Immediate
```

**Variáveis de Ambiente**:
```bash
RAIJIN_NAS_TYPE=synology
RAIJIN_NAS_IP=192.168.1.200
RAIJIN_NAS_SHARE=/volume1/kubernetes
RAIJIN_NAS_USER=k8s-admin
RAIJIN_NAS_PASSWORD=...  # Ou via Vault
RAIJIN_STORAGE_CLASS_DEFAULT=nas-ssd
```

---

### 4. `multiwan.py` - Multi-Link Internet

**Propósito**: Gerenciar múltiplos links de internet com failover e load balancing.

**Comandos CLI**:
```bash
raijin multiwan setup               # Configura multi-WAN
raijin multiwan add <interface>     # Adiciona link
raijin multiwan status              # Status dos links
raijin multiwan failover test       # Testa failover
raijin multiwan balance <algorithm> # round-robin|weighted|failover
```

**Cenários Suportados**:
- [ ] Dual ISP com failover automático
- [ ] Load balancing entre múltiplos IPs públicos
- [ ] CGNAT bypass com múltiplos túneis
- [ ] BGP com ASN próprio (enterprise)
- [ ] Wireguard multi-path

**Arquitetura Multi-IP**:
```
                    ┌─────────────────┐
                    │   Internet      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         ISP Link 1    ISP Link 2    ISP Link 3
         (200.x.x.1)   (200.x.x.2)   (200.x.x.3)
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────┴────────┐
                    │   pfSense/VyOS  │
                    │   Multi-WAN     │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  Control Plane  │
                    │   (Raijin)      │
                    └─────────────────┘
```

**Variáveis de Ambiente**:
```bash
RAIJIN_WAN_PRIMARY=eth0
RAIJIN_WAN_SECONDARY=eth1
RAIJIN_WAN_BALANCE=weighted
RAIJIN_WAN_WEIGHTS=70,30
RAIJIN_WAN_FAILOVER_CHECK=1.1.1.1
RAIJIN_WAN_FAILOVER_TIMEOUT=5
```

---

### 5. `poweredge.py` - Suporte Dell PowerEdge

**Propósito**: Integrações específicas para servidores Dell PowerEdge.

**Comandos CLI**:
```bash
raijin poweredge detect             # Detecta hardware Dell
raijin poweredge idrac setup        # Configura iDRAC
raijin poweredge firmware check     # Verifica firmware
raijin poweredge health             # Saúde do hardware
```

**Funcionalidades**:
- [ ] Detecção automática via DMI/SMBIOS
- [ ] Integração com iDRAC (IPMI/Redfish)
- [ ] Alertas de hardware (temperatura, discos, fans)
- [ ] RAID management via OpenManage
- [ ] Power capping e profiles
- [ ] Lifecycle Controller updates

**Requisitos de Hardware**:
| Modelo | CPU | RAM Min | Discos | Rede |
|--------|-----|---------|--------|------|
| R640 | 2x Xeon | 64GB | 8x SAS/SSD | 4x 10GbE |
| R740 | 2x Xeon | 128GB | 16x SAS/SSD | 4x 25GbE |
| R750 | 2x Xeon Ice Lake | 256GB | 24x NVMe | 4x 100GbE |

**Integração iDRAC**:
```bash
RAIJIN_IDRAC_IP=192.168.1.100
RAIJIN_IDRAC_USER=root
RAIJIN_IDRAC_PASSWORD=...  # Via Vault
RAIJIN_IDRAC_ALERTS=true
RAIJIN_IDRAC_WEBHOOK=https://alerts.domain.com/webhook
```

---

## 🏗️ Arquitetura Multi-Node

### Topologia Recomendada

```
                           ┌──────────────────────────────────────────┐
                           │              INTERNET                     │
                           └───────────────────┬──────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────┐
                    │                          │                      │
               ISP Link 1                 ISP Link 2             ISP Link 3
               200.x.x.1                  200.x.x.2              200.x.x.3
                    │                          │                      │
                    └──────────────────────────┼──────────────────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │   pfSense/OPNsense  │
                                    │   (Multi-WAN + VPN) │
                                    └──────────┬──────────┘
                                               │
           ┌───────────────────────────────────┼───────────────────────────────────┐
           │                                   │                                   │
   ┌───────┴───────┐                 ┌─────────┴─────────┐               ┌─────────┴─────────┐
   │ Control Plane │                 │  Worker Node 1    │               │  Worker Node 2    │
   │   (Notebook)  │                 │ (Dell R640/R740)  │               │ (Dell R640/R740)  │
   │               │                 │                   │               │                   │
   │ • kubeadm     │                 │ • kubelet         │               │ • kubelet         │
   │ • etcd        │                 │ • containerd      │               │ • containerd      │
   │ • api-server  │                 │ • calico-node     │               │ • calico-node     │
   │ • scheduler   │                 │ • GPU (opcional)  │               │ • GPU (opcional)  │
   │ • controller  │                 │                   │               │                   │
   └───────────────┘                 └───────────────────┘               └───────────────────┘
           │                                   │                                   │
           └───────────────────────────────────┼───────────────────────────────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │        NAS          │
                                    │ (Synology/TrueNAS)  │
                                    │                     │
                                    │ • NFS Shares        │
                                    │ • iSCSI Targets     │
                                    │ • Backup Storage    │
                                    └─────────────────────┘
```

### Fluxo de Deploy

```
1. Control Plane (Notebook)
   └── raijin full-install
       ├── bootstrap
       ├── kubernetes init
       ├── calico
       └── metallb

2. Worker Preparation (remoto via SSH)
   └── raijin worker prepare 192.168.1.101
       ├── install containerd
       ├── install kubeadm/kubelet
       └── configure kernel

3. Worker Join
   └── raijin worker add worker-01 --ip 192.168.1.101
       ├── generate join token
       ├── SSH execute kubeadm join
       └── verify node ready

4. Storage Setup
   └── raijin storage nas add 192.168.1.200
       ├── install nfs-csi-driver
       ├── create StorageClass
       └── test PVC provisioning

5. Workloads Deploy
   └── raijin install prometheus grafana loki
       ├── schedule to workers
       └── use NAS for persistence
```

---

## 📊 Requisitos de Hardware (Recomendados)

### Control Plane (Mínimo)
| Componente | Requisito |
|------------|-----------|
| CPU | 4 cores |
| RAM | 8GB |
| Disco | 50GB SSD |
| Rede | 1Gbps |

### Worker Node (Produção)
| Componente | Requisito |
|------------|-----------|
| CPU | 8+ cores (Xeon/EPYC) |
| RAM | 32GB+ |
| Disco | 256GB+ NVMe |
| Rede | 10Gbps+ |

### NAS (Recomendado)
| Componente | Requisito |
|------------|-----------|
| Tipo | Synology DS1821+ / TrueNAS |
| Discos | 4x SSD + 4x HDD (tiering) |
| RAM | 32GB ECC |
| Rede | 10GbE ou 2x 2.5GbE LAG |

---

## 🔐 Segurança Multi-Node

### Network Policies
```yaml
# Isolar workers por zona
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: zone-isolation
  namespace: production
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          zone: production
```

### mTLS entre Nodes
- Calico com WireGuard encryption
- Istio service mesh (opcional)
- Certificados rotativos via cert-manager

### Secrets Management
- HashiCorp Vault para credenciais de workers
- External Secrets Operator para NAS credentials
- Sealed Secrets para GitOps

---

## 📅 Roadmap de Desenvolvimento

### Fase 1: Foundation (Q1)
- [ ] `worker.py` - Add/Remove workers
- [ ] `cluster.py` - Basic cluster operations
- [ ] Documentação multi-node

### Fase 2: Storage (Q2)
- [ ] `storage.py` - Longhorn integration
- [ ] NFS CSI driver setup
- [ ] NAS auto-discovery

### Fase 3: Enterprise (Q3)
- [ ] `multiwan.py` - Multi-link support
- [ ] `poweredge.py` - Dell integration
- [ ] iDRAC alerts

### Fase 4: HA (Q4)
- [ ] Multi-master control plane
- [ ] etcd cluster (3 nodes)
- [ ] API server load balancing

---

## 🧪 Ambiente de Testes

### Lab Setup Recomendado
```
┌────────────────────────────────────────────────────────┐
│                    Home Lab Setup                       │
├────────────────────────────────────────────────────────┤
│                                                        │
│  [Router/Firewall]                                     │
│       │                                                │
│  [Switch 10GbE]                                        │
│       │                                                │
│  ┌────┴────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │ Control │  │ Worker1 │  │ Worker2 │  │   NAS   │  │
│  │ (Mini   │  │ (Dell   │  │ (Dell   │  │(Synology│  │
│  │  PC)    │  │  R640)  │  │  R640)  │  │ DS920+) │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
│                                                        │
│  Custo estimado: R$ 15-25k (usado)                    │
└────────────────────────────────────────────────────────┘
```

### VMs para Desenvolvimento
```bash
# Criar VMs com Multipass
multipass launch --name control -c 4 -m 8G -d 50G
multipass launch --name worker1 -c 4 -m 8G -d 50G
multipass launch --name worker2 -c 4 -m 8G -d 50G

# Instalar Raijin no control
multipass exec control -- bash -c "pip install raijin-server"
multipass exec control -- sudo raijin full-install
```

---

## 📝 Notas de Implementação

### Prioridades
1. **worker.py** é o módulo mais crítico - habilita toda a arquitetura multi-node
2. **storage.py** é necessário antes de deployar workloads stateful em workers
3. **multiwan.py** pode ser implementado independentemente
4. **poweredge.py** é "nice to have" para ambientes enterprise

### Breaking Changes Esperadas
- Configuração de rede pode migrar completamente para env vars
- Estrutura de estado em `/var/lib/raijin-server/` pode mudar
- Novos comandos CLI podem depreciar comandos antigos

### Compatibilidade
- Manter retrocompatibilidade com instalações single-node
- Detectar automaticamente se é multi-node ou single-node
- Migração assistida de single para multi-node

---

## 🤝 Contribuição

Para contribuir com a v2.0.0:

1. Escolha um módulo do backlog
2. Crie uma branch: `feature/v2-worker-module`
3. Implemente seguindo os padrões existentes
4. Adicione testes em `tests/test_<module>.py`
5. Atualize documentação em `docs/tools/`
6. Abra PR com descrição detalhada

---

## 📚 Referências

- [Kubernetes Multi-Node Setup](https://kubernetes.io/docs/setup/production-environment/)
- [Longhorn Distributed Storage](https://longhorn.io/docs/)
- [Dell iDRAC Redfish API](https://developer.dell.com/apis/2978/versions/6.xx/reference)
- [Calico eBPF Dataplane](https://docs.tigera.io/calico/latest/operations/ebpf/)
- [NFS CSI Driver](https://github.com/kubernetes-csi/csi-driver-nfs)
