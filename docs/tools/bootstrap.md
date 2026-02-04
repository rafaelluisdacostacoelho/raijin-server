# Bootstrap — Instalação de Ferramentas Base

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: MetalLB](metallb.md) | [Próximo: Loki →](loki.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Ferramentas instaladas](#ferramentas-instaladas)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **Bootstrap** é o módulo de **inicialização** do ambiente Raijin Server.
- Instala todas as ferramentas CLI necessárias para operação do cluster.
- Configura **[containerd](#1-containerd)¹** como **[CRI](#2-cri)²** (Container Runtime Interface).

## Por que usamos
- **Automação**: Uma única etapa instala todas as dependências.
- **Idempotência**: Detecta ferramentas já instaladas e pula reinstalação.
- **Configuração correta**: Aplica best practices (SystemdCgroup, swap desabilitado).
- **Versões fixas**: Garante compatibilidade entre componentes.

## Como está configurado no Raijin (V1)
- **Módulo CLI**: `raijin bootstrap`
- **Execução**: Requer `root` (instala binários em `/usr/local/bin`)
- **Ferramentas instaladas**:
  - **Helm** 3.14+ (package manager)
  - **kubectl** 1.30+ (CLI Kubernetes)
  - **istioctl** 1.21+ (service mesh)
  - **velero** 1.13+ (backup/restore)
  - **containerd** (container runtime)
- **Configurações aplicadas**:
  - Swap desabilitado (requisito K8s)
  - Módulos kernel: `overlay`, `br_netfilter`
  - Sysctl: `net.ipv4.ip_forward=1`, `bridge-nf-call-iptables=1`
  - Containerd com SystemdCgroup habilitado

## Ferramentas instaladas

| Ferramenta | Versão | Finalidade | Instalação |
|------------|--------|------------|------------|
| **[Helm](#3-helm)³** | 3.14.0 | Package manager K8s | Script oficial |
| **[kubectl](#4-kubectl)⁴** | 1.30.0 | CLI Kubernetes | Binary oficial |
| **[istioctl](#5-istioctl)⁵** | 1.21.0 | CLI Istio service mesh | Binary oficial |
| **[velero](#6-velero)⁶** | 1.13.0 | CLI backup/restore | Binary oficial |
| **[containerd](#1-containerd)¹** | Latest APT | Container runtime | APT package |

## Como operamos

### Executar bootstrap

```bash
# Modo normal (requer sudo)
sudo raijin bootstrap

# Dry-run (sem aplicar mudanças)
sudo raijin bootstrap --dry-run

# Verificar instalação
helm version
kubectl version --client
istioctl version --remote=false
velero version --client-only
containerd --version
```

### Validar configuração

```bash
# Verificar swap desabilitado
free -h | grep Swap
# Swap: 0B usado

# Verificar módulos kernel
lsmod | grep -E "overlay|br_netfilter"

# Verificar sysctl
sysctl net.ipv4.ip_forward
sysctl net.bridge.bridge-nf-call-iptables

# Status containerd
systemctl status containerd
```

### Reinstalar ferramenta específica

```bash
# Remover versão antiga
sudo rm /usr/local/bin/kubectl

# Executar bootstrap novamente (detecta ausência)
sudo raijin bootstrap
```

## Troubleshooting

### Helm não instalado

```bash
# Verificar conectividade
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3

# Instalar manualmente
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verificar PATH
echo $PATH | grep /usr/local/bin
```

### kubectl incompatível com cluster

```bash
# Ver versão do cluster
kubectl version

# Instalar versão específica
curl -LO "https://dl.k8s.io/release/v1.29.0/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### Containerd não inicia

```bash
# Ver logs
journalctl -xeu containerd

# Verificar config
cat /etc/containerd/config.toml | grep SystemdCgroup
# SystemdCgroup = true

# Regenerar config
sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd
```

### Swap não desabilita

```bash
# Verificar partições swap
cat /proc/swaps

# Desabilitar permanentemente
sudo swapoff -a
sudo sed -i '/swap/d' /etc/fstab

# Verificar fstab
cat /etc/fstab | grep swap
# (não deve retornar nada)
```

### Secure Boot bloqueando módulos

```bash
# Verificar Secure Boot
mokutil --sb-state
# SecureBoot enabled

# Assinar módulos (necessário para DKMS)
sudo apt install mokutil
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der

# Ou desabilitar Secure Boot na BIOS
```

## Glossário

### 1. containerd
**containerd**: Runtime de containers CNCF-incubated; alternativa ao Docker para Kubernetes.
- **[containerd.io](https://containerd.io/)**

### 2. CRI
**CRI**: Container Runtime Interface; especificação que define como kubelet interage com runtimes (containerd, CRI-O).
- **[kubernetes.io/docs/concepts/architecture/cri](https://kubernetes.io/docs/concepts/architecture/cri/)**

### 3. Helm
**Helm**: Package manager para Kubernetes; gerencia Charts (aplicações empacotadas).
- **[helm.sh](https://helm.sh/)**

### 4. kubectl
**kubectl**: CLI oficial do Kubernetes; controla clusters via API server.
- **[kubernetes.io/docs/reference/kubectl](https://kubernetes.io/docs/reference/kubectl/)**

### 5. istioctl
**istioctl**: CLI do Istio; instala/configura service mesh.
- **[istio.io/latest/docs/reference/commands/istioctl](https://istio.io/latest/docs/reference/commands/istioctl/)**

### 6. Velero
**Velero**: Ferramenta de backup/restore para Kubernetes (recursos + PVs).
- **[velero.io](https://velero.io/)**

### 7. SystemdCgroup
**SystemdCgroup**: Configura containerd para usar cgroups v2 via systemd (recomendado para K8s).

### 8. Swap
**Swap**: Memória virtual em disco; deve ser desabilitado no Kubernetes para evitar degradação de performance.

### 9. br_netfilter
**br_netfilter**: Módulo kernel que habilita iptables em bridge networks (necessário para CNI).

### 10. Idempotência
**Idempotência**: Propriedade que permite executar operação múltiplas vezes sem efeitos colaterais.

---

## Exemplos práticos

### Verificar instalação

```bash
# Script de validação
#!/bin/bash

echo "=== Verificando ferramentas ==="

check_tool() {
  if command -v $1 &> /dev/null; then
    echo "✓ $1: $($1 version --short 2>/dev/null || echo 'instalado')"
  else
    echo "✗ $1: NÃO INSTALADO"
  fi
}

check_tool helm
check_tool kubectl
check_tool istioctl
check_tool velero
check_tool containerd

echo -e "\n=== Verificando configuração ==="

echo -n "Swap: "
[[ $(free | grep Swap | awk '{print $2}') -eq 0 ]] && echo "✓ desabilitado" || echo "✗ ATIVO"

echo -n "br_netfilter: "
lsmod | grep -q br_netfilter && echo "✓ carregado" || echo "✗ ausente"

echo -n "ip_forward: "
[[ $(sysctl -n net.ipv4.ip_forward) -eq 1 ]] && echo "✓ habilitado" || echo "✗ desabilitado"
```

### Configuração manual containerd

```toml
# /etc/containerd/config.toml
version = 2

[plugins."io.containerd.grpc.v1.cri"]
  sandbox_image = "registry.k8s.io/pause:3.9"

[plugins."io.containerd.grpc.v1.cri".containerd]
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
    runtime_type = "io.containerd.runc.v2"
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
      SystemdCgroup = true  # CRÍTICO para K8s

[plugins."io.containerd.grpc.v1.cri".registry]
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
      endpoint = ["https://registry-1.docker.io"]
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."harbor.local.io"]
      endpoint = ["https://harbor.local.io"]
```

### Sysctl para Kubernetes

```bash
# /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1

# Aplicar
sudo sysctl --system

# Verificar
sysctl -a | grep -E "bridge-nf-call|ip_forward"
```

### Módulos kernel

```bash
# /etc/modules-load.d/k8s.conf
overlay
br_netfilter

# Carregar manualmente
sudo modprobe overlay
sudo modprobe br_netfilter

# Verificar
lsmod | grep -E "overlay|br_netfilter"
```

---

## Boas práticas ✅

1. **Executar antes de tudo**: Bootstrap deve ser o primeiro módulo.
2. **Verificar pré-requisitos**: Kernel headers, conectividade, root.
3. **Anotar versões**: Documentar versões instaladas para troubleshooting.
4. **Validar pós-instalação**: Executar script de verificação.
5. **Desabilitar swap permanentemente**: Editar `/etc/fstab`.
6. **SystemdCgroup habilitado**: Crítico para cgroups v2.
7. **Módulos kernel persistentes**: Configurar `/etc/modules-load.d/`.
8. **Sysctl aplicado no boot**: Arquivo em `/etc/sysctl.d/`.
9. **Containerd como runtime**: Não usar Docker em clusters novos.
10. **Versões fixas**: Evitar `latest` em produção.
11. **Backup de configs**: Salvar `/etc/containerd/config.toml`.
12. **Monitorar containerd**: Logs em Loki/journald.
13. **Kernel atualizado**: Usar kernel 5.15+ para cgroups v2.
14. **Firewall configurado**: Liberar portas K8s (6443, 10250, etc).
15. **SELinux/AppArmor**: Configurar policies se habilitados.

---

## Práticas ruins ❌

1. **Pular bootstrap**: Instalar K8s sem ferramentas base.
2. **Deixar swap ativo**: Kubelet falha ou degrada performance.
3. **SystemdCgroup = false**: Causa problemas em cgroups v2.
4. **Módulos não persistentes**: `modprobe` sem `/etc/modules-load.d/`.
5. **Sysctl não aplicado no boot**: Configuração perdida em reboot.
6. **Docker como runtime**: Deprecado no K8s 1.24+.
7. **Misturar containerd e Docker**: Causa conflitos.
8. **Não verificar instalação**: Descobrir problema só no `kubeadm init`.
9. **Secure Boot sem assinatura**: Módulos DKMS não carregam.
10. **Versões incompatíveis**: kubectl 1.30 com cluster 1.25.
11. **Instalar via snap**: Versões desatualizadas e path quebrado.
12. **Root privileges esquecidos**: Bootstrap falha sem sudo.
13. **Conectividade não testada**: Download de binários falha.
14. **Config containerd editado manualmente**: Perdido no upgrade.
15. **Não documentar customizações**: Dificulta troubleshooting.

---

## Diagnóstico avançado

### Ver versões instaladas

```bash
# Script completo
cat << 'EOF' > /tmp/versions.sh
#!/bin/bash
echo "=== Versões instaladas ==="
for tool in helm kubectl istioctl velero containerd; do
  if command -v $tool &> /dev/null; then
    ver=$($tool version --short 2>/dev/null || $tool --version 2>/dev/null || echo "?")
    echo "$tool: $ver"
  else
    echo "$tool: NOT FOUND"
  fi
done
EOF
chmod +x /tmp/versions.sh
/tmp/versions.sh
```

### Debug containerd

```bash
# Status detalhado
systemctl status containerd -l

# Logs em tempo real
journalctl -xefu containerd

# Ver config aplicada
containerd config dump

# Testar runtime
sudo ctr version
sudo ctr containers ls
```

### Verificar módulos kernel

```bash
# Listar módulos carregados
lsmod | grep -E "overlay|br_netfilter|nf_conntrack"

# Ver info de módulo
modinfo overlay
modinfo br_netfilter

# Forçar carregamento
sudo modprobe -v overlay
sudo modprobe -v br_netfilter
```

### Testar conectividade

```bash
# Helm script
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | head -n 5

# kubectl binary
curl -fsSL -I https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl

# istioctl
curl -fsSL -I https://github.com/istio/istio/releases/download/1.21.0/istio-1.21.0-linux-amd64.tar.gz

# Velero
curl -fsSL -I https://github.com/vmware-tanzu/velero/releases/download/v1.13.0/velero-v1.13.0-linux-amd64.tar.gz
```

### Reinstalar do zero

```bash
# Remover binários
sudo rm -f /usr/local/bin/{helm,kubectl,istioctl,velero}

# Remover containerd
sudo systemctl stop containerd
sudo apt remove -y containerd
sudo rm -rf /etc/containerd

# Limpar configs
sudo rm -f /etc/modules-load.d/k8s.conf
sudo rm -f /etc/sysctl.d/k8s.conf

# Reexecutar bootstrap
sudo raijin bootstrap
```

### Verificar Secure Boot

```bash
# Status Secure Boot
mokutil --sb-state

# Listar módulos não assinados
sudo dmesg | grep -i "loading out-of-tree module"

# Assinar módulos DKMS
sudo kmodsign sha512 /var/lib/shim-signed/mok/MOK.priv \
                      /var/lib/shim-signed/mok/MOK.der \
                      /path/to/module.ko
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: MetalLB](metallb.md)** | **[Próximo: Loki →](loki.md)**
