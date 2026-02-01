# Acesso remoto via VPN (WireGuard)

Como usar o módulo `vpn` do Raijin Server para acessar servidores fora da mesma rede usando WireGuard.

## Quando usar
- Acesso administrativo seguro quando o servidor está atrás de NAT/roteador ou em outra localidade.
- Expor apenas a porta UDP da VPN (em vez de abrir SSH direto na internet).

## Pré-requisitos
- Servidor Ubuntu com `raijin-server` instalado e privilégios de root (use `sudo -E ~/.venvs/midgard/bin/raijin-server vpn`).
- Porta UDP liberada externamente (padrão 51820). Em roteadores/ISP, faça port forward dessa porta para o host.
- Cliente WireGuard instalado no dispositivo remoto (Windows/macOS/Linux/iOS/Android). No Windows use o app "WireGuard" da Store ou do site oficial.

## Execução do módulo `vpn`
No servidor:

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server vpn
```

Prompts principais (valores sugeridos):
- Interface WireGuard: `wg0`
- Rede VPN (CIDR): `10.8.0.0/24`
- IP do servidor na VPN: primeiro host da rede (ex.: `10.8.0.1/24`).
- Nome/IP do cliente inicial: `admin` e `10.8.0.2/32` (primeiro cliente).
- Porta WireGuard: `51820`
- IP/Domínio público: IP fixo ou DNS que resolve para o servidor (necessário para clientes externos).
- Interface de saída (NAT): normalmente `eth0` (ajuste conforme `ip a`).
- DNS entregues aos clientes: `1.1.1.1,8.8.8.8`

O módulo gera e aplica:
- Configuração do servidor em `/etc/wireguard/wg0.conf`.
- Cliente inicial em `/etc/wireguard/clients/<nome>.conf`.
- Habilita IP forwarding (`/etc/sysctl.d/99-wireguard.conf`).
- Abre a porta UDP escolhida no UFW e sobe o serviço `wg-quick@wg0`.

## Entregar o cliente para Windows
1) Copie `/etc/wireguard/clients/<nome>.conf` para sua máquina (via `scp` ou `sftp`).
2) No app WireGuard (Windows): `Add Tunnel` ➜ `Import tunnel(s) from file` e escolha o `.conf` copiado.
3) Conecte (toggle ON). A rota `10.8.0.0/24` e DNS configurados serão aplicados.

Dica: para transportar por QR code (mobile), no servidor: `qrencode -t ansiutf8 /etc/wireguard/clients/<nome>.conf`.

## Validar conexão
- No cliente: `ping 10.8.0.1` (IP do servidor na VPN).
- No servidor: `sudo wg show` para ver handshakes e transferências.
- Se não houver handshake, revise: porta/UDP liberada no firewall externo, endpoint correto, hora/sincronização do host.

## Adicionar novos clientes
- Gere novas chaves em `/etc/wireguard/clients/` com `wg genkey`/`wg pubkey`, crie um `<novo>.conf` seguindo o modelo inicial e adicione o peer correspondente ao `wg0.conf`.
- Após editar `wg0.conf`, recarregue: `sudo systemctl restart wg-quick@wg0`.

## Acesso seguro aos dashboards via VPN

Uma vez conectado à VPN, você pode acessar todos os serviços do cluster de forma segura usando port-forward:

### Instalar kubectl no cliente (Windows/Mac/Linux)
```bash
# Windows (via Chocolatey)
choco install kubernetes-cli

# macOS (via Homebrew)
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### Copiar kubeconfig do servidor
```bash
# No servidor, copie o kubeconfig
sudo cat /etc/kubernetes/admin.conf > ~/kubeconfig

# No cliente (Windows/WSL/Linux/Mac), copie via scp
scp user@10.8.0.1:~/kubeconfig ~/.kube/config

# Ou se estiver usando IP público
scp user@seu-servidor.com:~/kubeconfig ~/.kube/config
```

### Acessar dashboards via port-forward

**Grafana:**
```bash
kubectl -n observability port-forward svc/grafana 3000:80
# Acesse: http://localhost:3000
```

**Prometheus:**
```bash
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 9090:9090
# Acesse: http://localhost:9090
```

**Alertmanager:**
```bash
kubectl -n observability port-forward svc/kube-prometheus-stack-alertmanager 9093:9093
# Acesse: http://localhost:9093
```

**MinIO Console:**
```bash
kubectl -n minio port-forward svc/minio-console 9001:9001
# Acesse: http://localhost:9001
```

**Traefik Dashboard:**
```bash
kubectl -n kube-system port-forward svc/traefik 9000:9000
# Acesse: http://localhost:9000/dashboard/
```

### Dica: Usar múltiplas portas simultaneamente

**Método 1: Script Automatizado (Recomendado)**

```bash
# Use o script pronto que gerencia tudo automaticamente
~/raijin-server/scripts/port-forward-all.sh start

# Ver status
~/raijin-server/scripts/port-forward-all.sh status

# Parar todos
~/raijin-server/scripts/port-forward-all.sh stop
```

**Método 2: Múltiplos Terminais**

Abra múltiplos terminais ou use um gerenciador de sessões:

```bash
# Terminal 1
kubectl -n observability port-forward svc/grafana 3000:80

# Terminal 2
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 9090:9090

# Terminal 3
kubectl -n minio port-forward svc/minio-console 9001:9001
```

Ou use um script:
```bash
#!/bin/bash
kubectl -n observability port-forward svc/grafana 3000:80 &
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 9090:9090 &
kubectl -n minio port-forward svc/minio-console 9001:9001 &
wait
```

## Boas práticas
- Use DNS público estável ou registro dinâmico para o endpoint.
- Mantenha a porta WireGuard aberta no firewall/roteador apenas no protocolo UDP.
- Se estiver em cloud com IP público direto, confirme que a security group/liberação de porta está ativa.
- Guarde os arquivos `.key` somente no servidor; distribua apenas os `.conf` dos clientes.

## Ferramentas Visuais

Para uma melhor experiência de gerenciamento, considere usar ferramentas visuais:

- **Lens:** IDE gráfica para Kubernetes ([docs/VISUAL_TOOLS.md](VISUAL_TOOLS.md))
- **K9s:** Interface terminal interativa ([docs/VISUAL_TOOLS.md](VISUAL_TOOLS.md))
- **Script de port-forward automático:** `scripts/port-forward-all.sh`

## Gerenciamento de Clientes

Use o módulo dedicado para gerenciar clientes VPN facilmente:

```bash
# Menu interativo
sudo raijin vpn-client

# Opções:
# 1. Adicionar cliente - Cria novo cliente com chaves e configuração
# 2. Listar clientes - Mostra todos os clientes configurados
# 3. Remover cliente - Remove cliente e revoga acesso
# 4. Mostrar configuração - Exibe .conf de um cliente
```

Veja documentação completa em [docs/VISUAL_TOOLS.md](VISUAL_TOOLS.md).
