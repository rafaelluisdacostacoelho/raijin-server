# Cloudflare Setup - Quick Start

## Passo a Passo: Configurar supabase.cryptidnest.com

### 1. Acessar Cloudflare Dashboard

```
https://dash.cloudflare.com/
→ Selecione: cryptidnest.com
→ Vá para: DNS → Records
```

### 2. Adicionar Registro DNS

Clique em **"Add record"**:

```
┌─────────────────────────────────────────┐
│ Type:    A                              │
│ Name:    supabase                       │
│ IPv4:    <SEU-IP-SERVIDOR>              │
│ Proxy:   🔘 DNS only (cinza)            │
│ TTL:     Auto                           │
└─────────────────────────────────────────┘
```

**⚠️ IMPORTANTE**: 
- ✅ **Proxy: OFF** (ícone cinza) para cert-manager funcionar
- ❌ **NÃO use Proxy ON** (ícone laranja) na primeira configuração

### 3. Salvar

Clique em **"Save"**

Aguarde **2-5 minutos** para propagação DNS.

### 4. Verificar DNS

No terminal do seu servidor:

```bash
# Deve retornar o IP do seu servidor
dig +short supabase.cryptidnest.com

# Ou usar nslookup
nslookup supabase.cryptidnest.com
```

### 5. Deploy Supabase

Agora pode fazer o deploy do Supabase:

```bash
raijin-server supabase install \
  --domain supabase.cryptidnest.com \
  --postgres-pass senhasegura123 \
  --namespace supabase
```

O comando irá:
1. ✅ Criar namespace `supabase`
2. ✅ Deploy PostgreSQL com PVC
3. ✅ Deploy Kong, PostgREST, GoTrue, Realtime, Storage
4. ✅ Configurar MinIO como backend de arquivos
5. ✅ Criar Ingress com Traefik
6. ✅ Solicitar certificado TLS ao Let's Encrypt
7. ✅ Configurar backup com Velero

### 6. Aguardar Certificado TLS

Acompanhe a emissão do certificado (1-2 minutos):

```bash
# Ver status do certificado
kubectl get certificate supabase-tls -n supabase -w

# Ver challenges (validação HTTP-01)
kubectl get challenges -n supabase

# Ver logs cert-manager
kubectl logs -n cert-manager deploy/cert-manager -f
```

Quando aparecer `READY: True`, o certificado foi emitido! ✅

### 7. Testar Acesso

```bash
# Teste HTTPS
curl -I https://supabase.cryptidnest.com

# Teste REST API
curl https://supabase.cryptidnest.com/rest/v1/

# Teste Auth API
curl https://supabase.cryptidnest.com/auth/v1/health

# Teste Realtime
curl https://supabase.cryptidnest.com/realtime/v1/health
```

### 8. Obter Credenciais Lovable

```bash
# Anon Key (pública - usar no frontend)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.anonKey}' | base64 -d

# Service Role Key (privada - usar no backend)
kubectl get secret supabase-jwt -n supabase -o jsonpath='{.data.serviceKey}' | base64 -d
```

### 9. Configurar no Lovable

No seu projeto Lovable, adicione as variáveis de ambiente:

```bash
# .env.local ou em Lovable Dashboard → Settings → Environment Variables
VITE_SUPABASE_URL=https://supabase.cryptidnest.com
VITE_SUPABASE_ANON_KEY=<anon-key-do-passo-8>
```

### 10. Testar Integração

No seu app Lovable:

```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)

// Testar conexão
const { data, error } = await supabase.from('_health').select('*')
console.log(data, error)
```

---

## Troubleshooting

### DNS não resolve

```bash
# 1. Verificar no Cloudflare que o registro foi criado
# 2. Aguardar 5 minutos
# 3. Limpar cache DNS local
sudo systemd-resolve --flush-caches

# 4. Testar com DNS do Cloudflare diretamente
dig @1.1.1.1 supabase.cryptidnest.com
```

### Certificado TLS não é criado

```bash
# 1. Verificar challenges
kubectl get challenges -n supabase
kubectl describe challenge <challenge-name> -n supabase

# 2. Verificar que porta 80 está aberta (HTTP-01 challenge)
curl http://supabase.cryptidnest.com/.well-known/acme-challenge/test

# 3. Se Cloudflare Proxy estiver ON (laranja), mude para OFF (cinza)
```

### Traefik não roteia

```bash
# 1. Verificar Ingress
kubectl get ingress -n supabase
kubectl describe ingress supabase-ingress -n supabase

# 2. Verificar Service Kong
kubectl get svc supabase-kong -n supabase

# 3. Ver logs Traefik
kubectl logs -n kube-system deploy/traefik -f
```

---

## Replicar para Outros Serviços

Para expor **outros serviços** (Harbor, Grafana, etc), basta repetir:

1. **Cloudflare**: Criar registro A (ex: `harbor → IP-SERVIDOR`)
2. **Ingress**: Criar Ingress resource apontando para o service
3. **cert-manager**: Emite certificado automaticamente via annotation

**Exemplo para Harbor**:

```yaml
# harbor.cryptidnest.com
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: harbor-ingress
  namespace: harbor
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - harbor.cryptidnest.com
    secretName: harbor-tls
  rules:
  - host: harbor.cryptidnest.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: harbor-portal
            port:
              number: 80
```

Veja guia completo: [DOMAIN_SETUP.md](DOMAIN_SETUP.md)

---

## Resumo Visual

```
┌─────────────────────────────────────────────────────────┐
│ 1. Cloudflare DNS                                       │
│    supabase.cryptidnest.com → A → IP-SERVIDOR           │
│    (Proxy: OFF - cinza)                                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Deploy Supabase                                      │
│    raijin-server supabase install                       │
│    --domain supabase.cryptidnest.com                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Traefik Ingress (criado automaticamente)            │
│    Host: supabase.cryptidnest.com                       │
│    Service: supabase-kong:8000                          │
│    TLS: supabase-tls (cert-manager)                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 4. cert-manager                                         │
│    Solicita certificado Let's Encrypt                   │
│    HTTP-01 challenge via Traefik                        │
│    Armazena em secret: supabase-tls                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 5. HTTPS Funcionando! ✅                                 │
│    https://supabase.cryptidnest.com                     │
└─────────────────────────────────────────────────────────┘
```

**Pronto!** Seu Supabase está acessível via HTTPS com certificado válido.

Agora configure as credenciais no Lovable e comece a desenvolver! 🚀
