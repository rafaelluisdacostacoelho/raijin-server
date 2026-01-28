# Exemplos Práticos - Raijin Server

## Exemplo 1: Primeira Instalação Completa

```bash
# 1. Clonar e instalar
git clone <repo-url> raijin-server
cd raijin-server
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Validar sistema
sudo .venv/bin/raijin-server validate

# 3. Executar sequência base
sudo .venv/bin/raijin-server essentials
sudo .venv/bin/raijin-server hardening
sudo .venv/bin/raijin-server network
sudo .venv/bin/raijin-server firewall

# 4. Kubernetes
sudo .venv/bin/raijin-server kubernetes
sudo .venv/bin/raijin-server calico

# 5. Monitoramento
sudo .venv/bin/raijin-server prometheus
sudo .venv/bin/raijin-server grafana
sudo .venv/bin/raijin-server loki

# 6. Verificar logs
sudo tail -f /var/log/raijin-server/raijin-server.log
```

---

## Exemplo 2: Uso com Configuração YAML

```bash
# 1. Gerar template
raijin-server generate-config -o production.yaml

# 2. Editar configuração
cat > production.yaml << EOF
global:
  dry_run: false
  max_retries: 3
  retry_delay: 5
  timeout: 300

modules:
  network:
    interface: ens18
    address: 192.168.1.10/24
    gateway: 192.168.1.1
    dns: 1.1.1.1,8.8.8.8
  
  kubernetes:
    pod_cidr: 10.244.0.0/16
    service_cidr: 10.96.0.0/12
    cluster_name: production-cluster
    advertise_address: 192.168.1.10
  
  grafana:
    namespace: observability
    admin_password: ${GRAFANA_PASSWORD}
    ingress_host: grafana.example.com
EOF

# 3. Configurar senha via env
export GRAFANA_PASSWORD="super-secret-password"

# 4. Executar com config
sudo -E raijin-server --config production.yaml essentials
sudo -E raijin-server --config production.yaml kubernetes
sudo -E raijin-server --config production.yaml grafana
```

---

## Exemplo 3: Teste com Dry-run

```bash
# Simular instalação completa sem aplicar
sudo raijin-server --dry-run essentials
sudo raijin-server --dry-run hardening
sudo raijin-server --dry-run network
sudo raijin-server --dry-run kubernetes

# Ver comandos que seriam executados
sudo raijin-server --dry-run kubernetes 2>&1 | grep "^\$"
```

---

## Exemplo 4: Recuperação de Falha

```bash
# Se um módulo falhar durante execução:

# 1. Verificar logs
sudo tail -100 /var/log/raijin-server/raijin-server.log

# 2. Verificar qual módulo falhou
ls -la /var/lib/raijin-server/state/

# 3. Corrigir problema e re-executar
sudo raijin-server kubernetes

# Sistema verifica estado e pula etapas já concluídas
```

---

## Exemplo 5: Automação CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy-server.yml
name: Deploy Ubuntu Server

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install raijin-server
        run: pip install -e .
      
      - name: Generate config
        run: raijin-server generate-config -o server-config.yaml
      
      - name: Deploy to server
        env:
          SSH_KEY: ${{ secrets.SSH_KEY }}
          SERVER_IP: ${{ secrets.SERVER_IP }}
        run: |
          echo "$SSH_KEY" > ssh_key
          chmod 600 ssh_key
          
          # Copiar config
          scp -i ssh_key server-config.yaml root@$SERVER_IP:/tmp/
          
          # Executar remoto
          ssh -i ssh_key root@$SERVER_IP << 'EOF'
            raijin-server --config /tmp/server-config.yaml essentials
            raijin-server --config /tmp/server-config.yaml kubernetes
          EOF
```

---

## Exemplo 6: Menu Interativo

```bash
# Iniciar menu
sudo raijin-server

# No menu:
# - Digite número do módulo para executar
# - Digite 't' para alternar dry-run
# - Digite 'sair' ou 'q' para sair
# - Veja status ✓ dos módulos concluídos
```

---

## Exemplo 7: Verificação de Dependências

```bash
# Tentar executar módulo sem dependências
sudo raijin-server calico

# Output:
# ✗ Modulo 'calico' requer os seguintes modulos executados primeiro: kubernetes
# Execute primeiro os modulos dependentes antes de 'calico'

# Ordem correta:
sudo raijin-server kubernetes
sudo raijin-server calico  # Agora funciona
```

---

## Exemplo 8: Health Check Manual

```bash
# Após instalar um módulo, verificar manualmente

# Kubernetes
kubectl get nodes
kubectl get pods -A

# Prometheus
kubectl get pods -n observability
helm status kube-prometheus-stack -n observability

# Grafana
kubectl get svc -n observability grafana
```

---

## Exemplo 9: Logs e Debugging

```bash
# Ver logs em tempo real
sudo tail -f /var/log/raijin-server/raijin-server.log

# Filtrar erros
sudo grep "ERROR" /var/log/raijin-server/raijin-server.log

# Ver últimos 50 comandos executados
sudo grep "Executando:" /var/log/raijin-server/raijin-server.log | tail -50

# Verificar health checks
sudo grep "Health check" /var/log/raijin-server/raijin-server.log
```

---

## Exemplo 10: Rollback Manual

```bash
# Se precisar reverter um módulo:

# 1. Remover state
sudo rm /var/lib/raijin-server/state/kubernetes.done

# 2. Reset do cluster (se Kubernetes)
sudo kubeadm reset -f
sudo rm -rf /etc/kubernetes /var/lib/kubelet /var/lib/etcd

# 3. Re-executar
sudo raijin-server kubernetes
```

---

## Exemplo 11: Configuração Multi-ambiente

```bash
# Desenvolvimento
cat > dev.yaml << EOF
global:
  dry_run: false

modules:
  kubernetes:
    cluster_name: dev-cluster
    pod_cidr: 10.244.0.0/16
EOF

# Staging
cat > staging.yaml << EOF
global:
  dry_run: false

modules:
  kubernetes:
    cluster_name: staging-cluster
    pod_cidr: 10.245.0.0/16
EOF

# Produção
cat > production.yaml << EOF
global:
  dry_run: false
  max_retries: 5

modules:
  kubernetes:
    cluster_name: production-cluster
    pod_cidr: 10.246.0.0/16
EOF

# Deploy por ambiente
sudo raijin-server --config dev.yaml kubernetes
sudo raijin-server --config staging.yaml kubernetes
sudo raijin-server --config production.yaml kubernetes
```

---

## Exemplo 12: Monitoramento de Execução

```bash
# Script para monitorar execução
cat > monitor.sh << 'EOF'
#!/bin/bash
watch -n 2 '
  echo "=== Status dos Módulos ==="
  ls -1 /var/lib/raijin-server/state/*.done 2>/dev/null | \
    xargs -n1 basename | sed "s/.done$//" | \
    awk "{print \"✓\", \$0}"
  
  echo ""
  echo "=== Últimas 5 Linhas do Log ==="
  tail -5 /var/log/raijin-server/raijin-server.log
'
EOF

chmod +x monitor.sh
./monitor.sh
```

---

## Exemplo 13: Validação Pré-Produção

```bash
#!/bin/bash
# pre-production-check.sh

echo "=== Checklist Pré-Produção ==="

# 1. Validar sistema
echo "1. Validando sistema..."
sudo raijin-server validate || exit 1

# 2. Dry-run de todos os módulos
echo "2. Testando dry-run..."
for module in essentials hardening network firewall kubernetes; do
  sudo raijin-server --dry-run $module || exit 1
done

# 3. Verificar configuração
echo "3. Verificando configuração..."
test -f production.yaml || exit 1

# 4. Verificar conectividade
echo "4. Testando conectividade..."
ping -c 1 8.8.8.8 || exit 1

# 5. Verificar espaço
echo "5. Verificando espaço em disco..."
df -h / | tail -1

echo ""
echo "✓ Sistema pronto para deploy em produção"
```

---

## Troubleshooting Comum

### Problema: Comando não encontrado
```bash
# Solução: Adicionar ao PATH ou usar caminho completo
export PATH="$PATH:$HOME/.local/bin"
# OU
/home/user/.local/bin/raijin-server validate
```

### Problema: Permissão negada em logs
```bash
# Solução: Criar diretório com permissões corretas
sudo mkdir -p /var/log/raijin-server
sudo chmod 755 /var/log/raijin-server

# OU usar variável de ambiente
export RAIJIN_STATE_DIR="$HOME/.raijin-server"
```

### Problema: Módulo falha com timeout
```bash
# Solução: Aumentar timeout via Python
python3 << EOF
from raijin_server.utils import ExecutionContext
ctx = ExecutionContext(timeout=600)  # 10 minutos
# Passar ctx para módulo
EOF

# OU editar utils.py temporariamente
```

### Problema: Dependências não satisfeitas
```bash
# Solução: Executar módulos na ordem
sudo raijin-server essentials
sudo raijin-server network
sudo raijin-server firewall
sudo raijin-server kubernetes  # Agora funciona
```

---

## Dicas de Performance

```bash
# 1. Usar config file para evitar prompts
raijin-server generate-config -o fast.yaml
sudo raijin-server --config fast.yaml kubernetes

# 2. Paralelizar em múltiplos servidores
for server in server1 server2 server3; do
  ssh root@$server "raijin-server essentials" &
done
wait

# 3. Cache de downloads (para múltiplas instalações)
# Criar mirror local de repos APT/Helm
```

---

**Mais exemplos no repositório em `examples/`**
