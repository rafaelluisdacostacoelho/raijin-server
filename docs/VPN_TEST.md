# Guia de Validação da VPN WireGuard

Este documento contém os procedimentos para validar se a VPN WireGuard está funcionando corretamente após configuração de port forwarding.

## 1️⃣ Verificar Status do WireGuard (Servidor)

```bash
# Status do serviço
sudo systemctl status wg-quick@wg0

# Se não estiver ativo, iniciar
sudo systemctl restart wg-quick@wg0

# Verificar se está escutando na porta
sudo ss -ulnp | grep 51820
# Deve mostrar: UNCONN 0.0.0.0:51820

# Ver configuração atual
sudo wg show
```

## 2️⃣ Reconectar Túnel (Cliente Windows)

1. Abra o app WireGuard
2. **Desconecte** o túnel "thor" (se estiver conectado)
3. Aguarde 5 segundos
4. **Conecte** novamente
5. Observe o status - deve ficar **verde** e mostrar "Active"

## 3️⃣ Verificar Handshake (CRÍTICO)

**No servidor:**

```bash
sudo wg show
```

### ✅ Conexão Funcionando

```
interface: wg0
  public key: vz6JbBJly5VXfDNI6VvHQENeWV66xCwX14oyoRgZOUU=
  private key: (hidden)
  listening port: 51820

peer: uLIlC4+0tpH505kdB3VytvO/ZYA3GVz5zMZt4gH3RBc=
  endpoint: 187.45.123.89:54321           ← IP do cliente + porta origem
  allowed ips: 10.8.0.2/32
  latest handshake: 15 seconds ago        ← Handshake recente
  transfer: 2.45 KiB received, 1.23 KiB sent  ← Dados trafegando
```

### ❌ Conexão NÃO Funcionando

```
interface: wg0
  public key: vz6JbBJly5VXfDNI6VvHQENeWV66xCwX14oyoRgZOUU=
  private key: (hidden)
  listening port: 51820

peer: uLIlC4+0tpH505kdB3VytvO/ZYA3GVz5zMZt4gH3RBc=
  allowed ips: 10.8.0.2/32
  # ← Falta endpoint, handshake e transfer
```

**Se não aparecer `endpoint`, `latest handshake` e `transfer` → há bloqueio!**

## 4️⃣ Testar Conectividade

### No Windows (PowerShell)

```powershell
# Ping para o servidor VPN
ping 10.8.0.1

# Deve responder:
# Reply from 10.8.0.1: bytes=32 time=20ms TTL=64

# Verificar interface VPN
ipconfig | findstr 10.8

# Deve mostrar:
# IPv4 Address. . . . . . . . . . . : 10.8.0.2

# Testar porta UDP (avançado)
Test-NetConnection -ComputerName IP_PUBLICO_SERVIDOR -Port 51820 -InformationLevel Detailed
```

### No Servidor

```bash
# Ping para o cliente (se Windows permitir ICMP)
ping -c 3 10.8.0.2
```

## 5️⃣ Acessar Serviços (Teste Final)

### Com DNS Interno

```
http://grafana.asgard.internal
http://prometheus.asgard.internal
http://minio.asgard.internal
```

### Por IP Direto

```bash
# No servidor, descobrir IPs dos serviços
kubectl get svc -A | grep -E "grafana|prometheus|minio"
```

Acesse no navegador Windows:
```
http://IP_DO_SERVICO:PORTA
```

---

## 🔧 Troubleshooting

### Handshake não aparece

#### 1. Verificar Log do WireGuard (Windows)

1. Abra o app WireGuard
2. Clique no túnel "thor"
3. Role até o final para ver logs
4. Procure por erros:
   - "Handshake did not complete after 5 seconds"
   - "No route to host"
   - "Connection refused"

#### 2. Verificar Endpoint Correto

Edite o túnel no Windows e confirme:

```ini
[Peer]
PublicKey = vz6JbBJly5VXfDNI6VvHQENeWV66xCwX14oyoRgZOUU=
Endpoint = IP_PUBLICO_SERVIDOR:51820  # ← IP público correto?
AllowedIPs = 10.8.0.0/24, 10.0.0.0/8
PersistentKeepalive = 25
```

**Confirme o IP público do servidor:**

```bash
curl ifconfig.me
```

#### 3. Testar Conectividade UDP

**No servidor (capturar pacotes):**

```bash
# Monitorar pacotes UDP na porta 51820
sudo tcpdump -i enp1s0 udp port 51820 -n

# Em outra aba, ver logs
sudo journalctl -u wg-quick@wg0 -f
```

**No Windows:** Reconecte o túnel e veja se aparecem pacotes no tcpdump.

**Se não aparecer nenhum pacote → port forwarding não está funcionando!**

#### 4. Verificar Firewall do Windows

**PowerShell (Admin):**

```powershell
# Ver regras do WireGuard
Get-NetFirewallRule -DisplayName "*wireguard*"

# Adicionar regra se necessário
New-NetFirewallRule -DisplayName "WireGuard Out" -Direction Outbound -Action Allow -Protocol UDP -RemotePort 51820
```

#### 5. Testar com Porta Alternativa

Se o provedor bloqueia porta 51820, tente 443/UDP:

**No servidor:**

```bash
sudo nano /etc/wireguard/wg0.conf
# Alterar: ListenPort = 443

sudo systemctl restart wg-quick@wg0
sudo ufw allow 443/udp
```

**No Windows (thor.conf):**

```ini
Endpoint = IP_PUBLICO:443
```

---

## ✅ Checklist Completo

Execute no servidor:

```bash
echo "=== 1. WireGuard Status ==="
sudo systemctl status wg-quick@wg0 | grep Active

echo -e "\n=== 2. Porta Escutando ==="
sudo ss -ulnp | grep 51820

echo -e "\n=== 3. Peers e Handshake ==="
sudo wg show

echo -e "\n=== 4. IP Público ==="
curl -s ifconfig.me

echo -e "\n=== 5. IP Forwarding ==="
cat /proc/sys/net/ipv4/ip_forward

echo -e "\n=== 6. Regras MASQUERADE ==="
sudo iptables -t nat -L POSTROUTING -v -n | grep -E "MASQUERADE|10.8"

echo -e "\n=== 7. Rotas ==="
ip route show | grep 10.8
```

---

## 📊 Interpretação dos Resultados

| Sintoma | Causa Provável | Solução |
|---------|----------------|---------|
| Handshake ausente | Port forwarding não funciona | Verificar provedor/router |
| Handshake presente, mas ping falha | IP forwarding ou MASQUERADE | `diagnose_and_fix` no vpn-client |
| Túnel conecta mas sem acesso | DNS não configurado | Usar IPs diretos ou configurar DNS |
| Timeout ao conectar | Endpoint errado | Confirmar IP público |
| Firewall Windows | Regra UDP 51820 ausente | Adicionar regra no firewall |

---

## 🚀 Comando Rápido de Diagnóstico

No servidor:

```bash
sudo -E raijin-server vpn-client
# Escolha opção 5: Diagnosticar e corrigir roteamento
```

Isso automaticamente:
- Verifica IP forwarding
- Adiciona regras MASQUERADE
- Configura UFW
- Reinicia WireGuard
- Mostra status dos peers
