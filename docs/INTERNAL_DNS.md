# DNS Interno para Domínios Privados

Este guia mostra como configurar DNS interno para acessar serviços administrativos usando domínios amigáveis como `grafana.asgard.internal` ao invés de port-forwards manuais.

## ⚠️ É Seguro em Ambientes Já Configurados?

**SIM!** O módulo é 100% não-invasivo:

✅ **Não altera** deployments, services, PVCs, secrets existentes  
✅ **Não requer** reinstalação ou reconfiguração de módulos  
✅ **Apenas adiciona** recursos novos (ConfigMap, Ingress)  
✅ **Pode ser revertido** facilmente sem impacto  

### O que É Alterado

| Recurso | Ação | Impacto |
|---------|------|---------|
| CoreDNS ConfigMap | Cria `coredns-custom` | Adiciona regras DNS, não altera principal |
| CoreDNS Deployment | Rollout restart | Aplica novo ConfigMap, sem downtime |
| Ingress | Cria novos com sufixo `-internal` | Não altera Ingress existentes |
| WireGuard | Atualiza linha `DNS =` | Opcional, pode fazer manualmente |

### O que NÃO É Alterado

❌ Grafana, Prometheus, MinIO (deployments)  
❌ Services (ClusterIP, LoadBalancer)  
❌ PersistentVolumeClaims (seus dados)  
❌ ConfigMaps (dashboards, alertas)  
❌ Secrets (credenciais, TLS)  
❌ Configuração do Traefik  

## 🔍 Validação Pré-Instalação

Antes de instalar, execute o script de validação para ver EXATAMENTE o que será alterado:

```bash
sudo /home/rafael/github/raijin-server/scripts/validate-internal-dns.sh
```

O script mostra:
- CoreDNS atual vs. o que será criado
- Serviços que serão configurados
- Ingress existentes (que não serão alterados)
- Novos Ingress que serão criados
- Estado do WireGuard
- Resumo completo de impacto

## Visão Geral

O módulo `internal_dns` configura:

1. **CoreDNS customizado** - Resolve domínios internos (*.asgard.internal) para o IP do nó
2. **Ingress interno** - Roteia requisições HTTP baseadas em hostname
3. **DNS no WireGuard** - Clientes VPN usam o DNS do cluster automaticamente

## Vantagens

✅ **URLs amigáveis** - `http://grafana.asgard.internal` ao invés de `localhost:3000`  
✅ **Sem port-forward** - Acesso direto via Ingress  
✅ **Múltiplos serviços** - Todos acessíveis simultaneamente sem conflito de portas  
✅ **Experiência profissional** - Simula ambiente de produção  

## Extensões Recomendadas

Segundo as RFCs, use extensões reservadas para redes privadas:

| Extensão | RFC | Uso Recomendado | Exemplo |
|----------|-----|-----------------|---------|
| `.internal` | RFC 6762 | ✅ Recomendado | `grafana.asgard.internal` |
| `.home.arpa` | RFC 8375 | ✅ Redes residenciais | `grafana.asgard.home.arpa` |
| `.local` | RFC 6762 | ⚠️ Pode conflitar com mDNS | `grafana.asgard.local` |
| `.test` | RFC 6761 | ⚠️ Apenas para testes | `grafana.asgard.test` |

**❌ EVITE** extensões reais: `.io`, `.com`, `.net`, `.org`, `.dev`

## Instalação

### 1. Execute o módulo

```bash
sudo raijin internal-dns
```

### 2. Configure o domínio

```
Domínio base (sem o ponto inicial): asgard.internal
```

O módulo irá:
- Detectar o IP do nó automaticamente
- Configurar CoreDNS para resolver `*.asgard.internal`
- Detectar serviços disponíveis (Grafana, Prometheus, MinIO, etc.)
- Criar Ingress interno para cada serviço
- Atualizar configuração do WireGuard (servidor e clientes)

### 3. Reinicie o WireGuard

**No servidor:**
```bash
sudo wg-quick down wg0
sudo wg-quick up wg0
```

**Nos clientes:**
- Distribua os novos arquivos `.conf` (em `/etc/wireguard/clients/`)
- Reconecte ao VPN

## Serviços Detectados Automaticamente

O módulo detecta e configura:

| Serviço | Namespace | Domínio Padrão |
|---------|-----------|----------------|
| Grafana | observability | `grafana.asgard.internal` |
| Prometheus | observability | `prometheus.asgard.internal` |
| Alertmanager | observability | `alertmanager.asgard.internal` |
| Loki | observability | `loki.asgard.internal` |
| MinIO Console | minio | `minio.asgard.internal` |
| Traefik Dashboard | traefik | `traefik.asgard.internal` |
| Kong Admin API | kong | `kong.asgard.internal` |

## Uso

### Conectar à VPN

```bash
# No servidor
sudo wg-quick up wg0

# No cliente (Linux)
sudo wg-quick up cliente1

# No cliente (Windows)
# Use o WireGuard GUI
```

### Acessar os serviços

Simplesmente abra o navegador e acesse:

```
http://grafana.asgard.internal
http://prometheus.asgard.internal
http://alertmanager.asgard.internal
http://minio.asgard.internal
```

**Não é necessário port-forward!** 🎉

## Testando a Resolução DNS

### No cluster

```bash
kubectl run -it --rm dns-test --image=busybox --restart=Never -- \
  nslookup grafana.asgard.internal
```

### No cliente VPN

```bash
# Linux/Mac
nslookup grafana.asgard.internal

# Windows PowerShell
Resolve-DnsName grafana.asgard.internal
```

Deve retornar o IP do nó do cluster (ex: `192.168.1.81`).

## Comparação: Port-Forward vs DNS Interno

### ❌ Antes (Port-Forward)

```bash
# Terminal 1
kubectl -n observability port-forward svc/grafana 3000:80

# Terminal 2
kubectl -n observability port-forward svc/kube-prometheus-stack-prometheus 9090:9090

# Terminal 3
kubectl -n minio port-forward svc/minio-console 9001:9001

# Navegador
http://localhost:3000  # Grafana
http://localhost:9090  # Prometheus
http://localhost:9001  # MinIO
```

**Problemas:**
- Múltiplos terminais abertos
- Conflitos de porta
- Precisa lembrar qual porta é qual serviço
- Reconectar após timeout

### ✅ Depois (DNS Interno)

```bash
# Conecta uma vez ao VPN
sudo wg-quick up wg0

# Navegador
http://grafana.asgard.internal
http://prometheus.asgard.internal
http://minio.asgard.internal
```

**Benefícios:**
- Uma conexão VPN
- URLs descritivas
- Acesso simultâneo a todos os serviços
- Conexão persistente

## Troubleshooting

### DNS não resolve

**1. Verifique o CoreDNS:**
```bash
kubectl get configmap coredns-custom -n kube-system
kubectl rollout status deployment/coredns -n kube-system
```

**2. Teste dentro do cluster:**
```bash
kubectl run -it --rm dns-test --image=busybox --restart=Never -- \
  nslookup grafana.asgard.internal
```

**3. Verifique configuração do cliente VPN:**
```bash
grep "DNS" /etc/wireguard/cliente1.conf
# Deve mostrar: DNS = <IP-DO-NÓ>
```

### Ingress não funciona

**1. Verifique se o Traefik está rodando:**
```bash
kubectl get pods -n traefik
```

**2. Verifique os Ingress criados:**
```bash
kubectl get ingress -A | grep internal
```

**3. Teste com curl:**
```bash
curl -H "Host: grafana.asgard.internal" http://<IP-DO-NÓ>
```

### Não consigo acessar do cliente VPN

**1. Verifique conectividade VPN:**
```bash
ping 10.8.0.1  # IP da VPN do servidor
```

**2. Verifique se o DNS está configurado:**
```bash
nslookup grafana.asgard.internal
# Deve resolver para o IP do nó
```

**3. Teste conectividade HTTP:**
```bash
curl -v http://grafana.asgard.internal
```

## Adicionando Novos Serviços

Para adicionar um novo serviço ao DNS interno:

### Método 1: Re-executar o módulo

```bash
sudo raijin internal-dns
```

O módulo detectará automaticamente novos serviços.

### Método 2: Criar Ingress manualmente

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: meu-servico-internal
  namespace: meu-namespace
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  ingressClassName: traefik
  rules:
    - host: meu-servico.asgard.internal
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: meu-servico
                port:
                  number: 80
```

```bash
kubectl apply -f ingress.yaml
```

## Integração com Ferramentas Visuais

O DNS interno funciona perfeitamente com:

### Lens IDE
Configure o kubeconfig via VPN e acesse os dashboards diretamente pelos links do Lens.

### K9s
Use `:svc` para listar serviços e pressione `Shift+F` para port-forward, mas agora você não precisa mais!

### Navegador
Crie favoritos:
- `http://grafana.asgard.internal`
- `http://prometheus.asgard.internal`
- `http://minio.asgard.internal`

## Segurança

### ✅ Boas Práticas

1. **Apenas via VPN** - DNS interno só resolve quando conectado ao VPN
2. **Sem TLS necessário** - Tráfego já é criptografado pelo WireGuard
3. **Sem exposição pública** - Domínios `.internal` não resolvem na internet
4. **Network Policies** - Combine com Calico para controle adicional

### ⚠️ Considerações

- DNS interno **não substitui** autenticação nos serviços
- Mantenha credenciais fortes (Grafana, MinIO, etc.)
- Use Network Policies para limitar acesso entre namespaces
- Considere adicionar basic-auth no Traefik para camada extra

## Migrando de Port-Forward para DNS Interno

1. **Instale o módulo internal-dns:**
   ```bash
   sudo raijin internal-dns
   ```

2. **Atualize documentação da equipe:**
   - Substitua instruções de port-forward por URLs diretas
   - Distribua novos arquivos `.conf` do VPN

3. **Opcional: Remova port-forward-all.sh**
   - Você não precisa mais do script de automação
   - Ou mantenha como fallback

4. **Teste todos os serviços:**
   ```bash
   # Conecte ao VPN
   sudo wg-quick up wg0
   
   # Teste cada serviço
   curl http://grafana.asgard.internal
   curl http://prometheus.asgard.internal/-/healthy
   curl http://minio.asgard.internal
   ```

## Recursos Adicionais

- [Documentação do CoreDNS](https://coredns.io/manual/toc/)
- [RFC 6762 - Special-Use Domain Names](https://datatracker.ietf.org/doc/html/rfc6762)
- [RFC 8375 - Special-Use Domain 'home.arpa'](https://datatracker.ietf.org/doc/html/rfc8375)
- [VPN Remote Access Guide](VPN_REMOTE_ACCESS.md)
- [Visual Tools Guide](VISUAL_TOOLS.md)
