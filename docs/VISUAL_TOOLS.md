# Ferramentas Visuais para Kubernetes via VPN

Guia de como usar ferramentas visuais de gerenciamento de Kubernetes através da VPN WireGuard.

## Pré-requisitos

1. VPN WireGuard configurada e conectada ([veja VPN_REMOTE_ACCESS.md](VPN_REMOTE_ACCESS.md))
2. Kubeconfig copiado do servidor
3. Conexão VPN ativa

## Opção 1: Lens (GUI - Recomendado para Iniciantes)

**Lens** é uma poderosa IDE para Kubernetes com interface gráfica moderna.

### Instalação

**Windows:**
```powershell
# Via winget
winget install Mirantis.Lens

# Ou baixe direto do site
# https://k8slens.dev/
```

**macOS:**
```bash
brew install --cask lens
```

**Linux:**
```bash
# Debian/Ubuntu
curl -fsSL https://downloads.k8slens.dev/keys/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/lens-archive-keyring.gpg > /dev/null
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/lens-archive-keyring.gpg] https://downloads.k8slens.dev/apt/debian stable main" | sudo tee /etc/apt/sources.list.d/lens.list > /dev/null
sudo apt update
sudo apt install lens

# Arch Linux
yay -S lens-bin
```

### Configuração

1. **Conecte à VPN WireGuard**

2. **Abra o Lens**

3. **Adicione o cluster:**
   - Clique em "+" ou "Add Cluster"
   - Selecione "Add from kubeconfig"
   - Navegue até `~/.kube/config`
   - Selecione o contexto do seu cluster

4. **Conecte ao cluster:**
   - Clique no cluster na lista
   - O Lens se conectará através da VPN

### Recursos do Lens

- **Dashboard visual:** CPU, memória, pods, serviços
- **Navegação fácil:** Browse por namespaces, workloads, config
- **Logs integrados:** Veja logs de pods em tempo real
- **Shell integrado:** Execute comandos dentro de pods
- **Port-forward visual:** Configure port-forwards com um clique
- **Helm charts:** Instale e gerencie releases Helm
- **Métricas:** Gráficos de uso de recursos

### Exemplo de Uso

1. **Ver pods em execução:**
   - Workloads → Pods
   - Filtre por namespace
   - Clique em um pod para detalhes

2. **Acessar logs:**
   - Clique em um pod
   - Tab "Logs"
   - Real-time streaming

3. **Port-forward com um clique:**
   - Clique em um service
   - "Forward" → Escolha portas
   - Acesse via localhost

4. **Shell em um pod:**
   - Clique em um pod
   - Tab "Pod Shell"
   - Terminal interativo

## Opção 2: K9s (TUI - Terminal UI)

**K9s** é uma interface terminal interativa para Kubernetes, perfeita para quem prefere trabalhar no terminal.

### Instalação

**Windows:**
```powershell
# Via Chocolatey
choco install k9s

# Via Scoop
scoop install k9s
```

**macOS:**
```bash
brew install k9s
```

**Linux:**
```bash
# Via snap
sudo snap install k9s

# Ou download direto
curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/

# Arch Linux
sudo pacman -S k9s
```

### Configuração

1. **Conecte à VPN WireGuard**

2. **Execute k9s:**
```bash
k9s
```

K9s automaticamente detecta `~/.kube/config` e se conecta via VPN.

### Atalhos Essenciais

| Tecla | Ação |
|-------|------|
| `:pod` | Ver pods |
| `:svc` | Ver services |
| `:deploy` | Ver deployments |
| `:ns` | Ver/mudar namespace |
| `/` | Filtrar/buscar |
| `l` | Ver logs do pod selecionado |
| `d` | Describe recurso |
| `e` | Editar recurso |
| `s` | Shell no pod |
| `ctrl-d` | Deletar recurso |
| `?` | Ajuda |
| `:q` | Sair |

### Exemplo de Uso

```bash
# Inicia K9s
k9s

# Ver pods do namespace observability
:ns observability
:pod

# Ver logs de um pod (selecione com ↑↓ e pressione 'l')
# Navegar logs: ↑↓ PgUp PgDn

# Shell em um pod (selecione e pressione 's')
# Sair do shell: exit ou Ctrl+D

# Ver services
:svc

# Port-forward (selecione service e pressione Shift+F)
# Digite porta local:porta remota
```

### Personalização do K9s

Crie `~/.config/k9s/config.yaml`:

```yaml
k9s:
  refreshRate: 2
  headless: false
  logoless: false
  crumbsless: false
  readOnly: false
  noExitOnCtrlC: false
  ui:
    skin: "dracula"  # Ou "monokai", "nord", "solarized-dark"
    logoless: false
    noIcons: false
  skipLatestRevCheck: true
  disablePodCounting: false
  shellPod:
    image: busybox:1.35.0
    command: []
    args: []
    namespace: default
    limits:
      cpu: 100m
      memory: 100Mi
```

## Opção 3: kubectl + kubectl-neat

Para quem prefere linha de comando pura, com output limpo.

### Instalação

```bash
# kubectl-neat remove campos desnecessários do output
kubectl krew install neat

# Ou via script
curl -Lo kubectl-neat https://github.com/itaysk/kubectl-neat/releases/latest/download/kubectl-neat_linux_amd64
chmod +x kubectl-neat
sudo mv kubectl-neat /usr/local/bin/
```

### Uso

```bash
# Output padrão (verboso)
kubectl get pod grafana-xxx -o yaml

# Output limpo
kubectl get pod grafana-xxx -o yaml | kubectl neat

# Ou com plugin
kubectl neat get pod grafana-xxx -o yaml
```

## Opção 4: Octant (GUI - Dashboard Web Local)

**Octant** roda um servidor web local para visualizar o cluster.

### Instalação

**Windows:**
```powershell
choco install octant
```

**macOS:**
```bash
brew install octant
```

**Linux:**
```bash
# Download direto
curl -Lo octant.tar.gz https://github.com/vmware-tanzu/octant/releases/latest/download/octant_0.25.1_Linux-64bit.tar.gz
tar -xzf octant.tar.gz
sudo mv octant_0.25.1_Linux-64bit/octant /usr/local/bin/
```

### Uso

```bash
# Conecte à VPN primeiro
octant

# Acesse: http://localhost:7777
```

## Comparação de Ferramentas

| Ferramenta | Interface | Recursos | Melhor Para |
|------------|-----------|----------|-------------|
| **Lens** | GUI (Desktop) | ★★★★★ Completo | Iniciantes, trabalho visual |
| **K9s** | TUI (Terminal) | ★★★★☆ Rico | Usuários CLI, SSH remoto |
| **Octant** | Web (localhost) | ★★★★☆ Bom | Preferem navegador |
| **kubectl** | CLI | ★★★★★ Completo | Scripts, automação |

## Recomendação

**Para administração diária:**
- **Lens** para tarefas visuais e exploração
- **K9s** para troubleshooting rápido
- **kubectl** para automação e scripts

**Workflow sugerido:**
1. Conecte à VPN
2. Use Lens para overview do cluster
3. Use K9s para troubleshooting e logs
4. Use kubectl para operações avançadas

## Troubleshooting

### Lens não conecta

```bash
# Verifique VPN
ping 10.8.0.1

# Teste kubectl
kubectl cluster-info

# Verifique contexto
kubectl config current-context

# Verifique permissões do kubeconfig
ls -la ~/.kube/config
```

### K9s fica lento

```bash
# Aumente intervalo de refresh no config
# ~/.config/k9s/config.yaml
k9s:
  refreshRate: 5  # segundos (padrão: 2)
```

### Timeout errors

```bash
# Verifique latência da VPN
ping -c 10 10.8.0.1

# Aumente timeout do kubectl
kubectl config set-context --current --timeout=30s

# Ou via variável de ambiente
export KUBECONFIG_TIMEOUT=30
```

## Scripts Úteis

### Script para verificar conexão

```bash
#!/bin/bash
# check-k8s-connection.sh

echo "Verificando conexão VPN..."
if ! ping -c 1 10.8.0.1 &>/dev/null; then
    echo "❌ VPN não conectada!"
    exit 1
fi
echo "✓ VPN OK"

echo "Verificando cluster Kubernetes..."
if ! kubectl cluster-info &>/dev/null; then
    echo "❌ Cluster não acessível!"
    exit 1
fi
echo "✓ Cluster OK"

echo "Verificando nodes..."
kubectl get nodes

echo "Verificando pods críticos..."
kubectl get pods -n kube-system
kubectl get pods -n observability

echo ""
echo "✓ Tudo pronto! Você pode usar Lens, K9s ou kubectl."
```

### Script para iniciar ambiente

```bash
#!/bin/bash
# start-k8s-tools.sh

# Verifica VPN
if ! ping -c 1 10.8.0.1 &>/dev/null; then
    echo "Conecte à VPN WireGuard primeiro!"
    exit 1
fi

# Inicia port-forwards em background
~/raijin-server/scripts/port-forward-all.sh start

# Aguarda um momento
sleep 3

# Inicia K9s ou Lens
read -p "Iniciar [1] Lens, [2] K9s, [3] Ambos? " choice

case $choice in
    1) lens & ;;
    2) k9s ;;
    3) lens & sleep 2 && k9s ;;
    *) echo "Opção inválida" ;;
esac
```

## Recursos Adicionais

- **Lens Documentação:** https://docs.k8slens.dev/
- **K9s Documentação:** https://k9scli.io/
- **kubectl Cheat Sheet:** https://kubernetes.io/docs/reference/kubectl/cheatsheet/
- **Octant:** https://octant.dev/

## Segurança

⚠️ **Importante:**

1. Nunca compartilhe seu arquivo `kubeconfig`
2. Use VPN sempre que acessar o cluster
3. Revise permissões RBAC regularmente
4. Monitore acessos através dos logs de audit do Kubernetes

```bash
# Ver logs de acesso (se audit logging estiver habilitado)
kubectl logs -n kube-system kube-apiserver-xxx | grep audit
```
