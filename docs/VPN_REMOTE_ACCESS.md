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

## Boas práticas
- Use DNS público estável ou registro dinâmico para o endpoint.
- Mantenha a porta WireGuard aberta no firewall/roteador apenas no protocolo UDP.
- Se estiver em cloud com IP público direto, confirme que a security group/liberação de porta está ativa.
- Guarde os arquivos `.key` somente no servidor; distribua apenas os `.conf` dos clientes.
