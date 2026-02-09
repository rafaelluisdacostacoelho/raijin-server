# Supabase — Segurança e Hardening

> **Navegação**: [← Voltar ao Índice](README.md) | [← Supabase Geral](supabase.md)

---

## Índice

- [Visão Geral](#visão-geral)
- [Auditoria de Segurança](#auditoria-de-segurança)
- [1. CORS — Controle de Origens](#1-cors--controle-de-origens)
- [2. Row Level Security (RLS)](#2-row-level-security-rls)
- [3. Kong — ClusterIP em vez de LoadBalancer](#3-kong--clusterip-em-vez-de-loadbalancer)
- [4. Rate Limiting](#4-rate-limiting)
- [5. MinIO — Acesso Interno](#5-minio--acesso-interno)
- [6. Security Headers (Traefik)](#6-security-headers-traefik)
- [7. GoTrue Hardening](#7-gotrue-hardening)
- [8. Network Policies](#8-network-policies)
- [Gerenciamento de Aplicações (CLI)](#gerenciamento-de-aplicações-cli)
- [Checklist de Segurança](#checklist-de-segurança)

---

## Visão Geral

O Supabase expõe diversas superfícies de ataque quando configurado com valores padrão. Este documento descreve as vulnerabilidades encontradas, os remédios aplicados, e como gerenciar o acesso de aplicações via CLI.

### Princípios

1. **Least Privilege**: Cada componente tem acesso apenas ao mínimo necessário
2. **Defense in Depth**: Múltiplas camadas de proteção (CORS → Rate Limit → RLS → Network Policy)
3. **Zero Trust**: Nenhum tráfego interno é confiável por padrão
4. **Allowlist**: Configuração explícita de origens permitidas

---

## Auditoria de Segurança

### Vulnerabilidades encontradas (antes do hardening)

| # | Severidade | Problema | Impacto |
|---|-----------|----------|---------|
| 1 | **CRÍTICA** | CORS aberto `origins: "*"` | Qualquer site pode fazer requests à API |
| 2 | **CRÍTICA** | RLS desabilitado em todas as tabelas | Anon key pode ler/escrever TUDO |
| 3 | **ALTA** | Kong tipo `LoadBalancer` (IP externo) | Bypass de TLS/Traefik via acesso direto |
| 4 | **ALTA** | Zero Rate Limiting | Vulnerável a brute force e DDoS |
| 5 | **ALTA** | MinIO exposto via `NodePort` | Console e API acessíveis na rede |
| 6 | **MÉDIA** | Sem Security Headers no Traefik | HSTS, X-Frame-Options ausentes |
| 7 | **MÉDIA** | Signup aberto + auto-confirm | Qualquer pessoa cria conta |
| 8 | **MÉDIA** | Sem Network Policies aplicadas | Pods falam com todos |

### O que já estava seguro

- ✅ PostgreSQL em ClusterIP (sem exposição externa)
- ✅ TLS Let's Encrypt válido
- ✅ HTTPS enforced via Traefik
- ✅ Sem Studio/Dashboard exposto publicamente

---

## 1. CORS — Controle de Origens

### Problema

```yaml
# ANTES (inseguro): aceita qualquer origem
origins:
  - "*"
```

Qualquer website na internet pode fazer requests ao seu Supabase via browser (XSS, CSRF).

### Solução

Restringir CORS apenas aos domínios das suas aplicações:

```yaml
# DEPOIS (seguro): apenas origens autorizadas
origins:
  - "https://supabase.cryptidnest.com"
  - "https://*.lovable.app"
```

### Gerenciamento via CLI

```bash
# Adicionar domínio ao CORS
raijin-server supabase-security cors-add --domain "https://meu-app.lovable.app"

# Remover domínio do CORS
raijin-server supabase-security cors-remove --domain "https://meu-app.lovable.app"

# Listar domínios autorizados
raijin-server supabase-security cors-list

# Status geral de segurança
raijin-server supabase-security status
```

### Como funciona

O CLI atualiza o ConfigMap `kong-config` no namespace `supabase`, alterando a lista de `origins` em todos os plugins CORS dos serviços Kong. Após atualizar, faz restart do pod Kong para aplicar a nova configuração declarativa.

---

## 2. Row Level Security (RLS)

### Problema

Sem RLS, a `anon_key` (exposta no frontend) funciona como chave admin — permite SELECT/INSERT/UPDATE/DELETE em **todas** as tabelas do schema `public`.

### Solução

Habilitar RLS em `storage.objects` e `storage.buckets`. Tabelas do schema `auth` são gerenciadas pelo GoTrue e não devem ter RLS habilitado manualmente.

```sql
-- Habilitar RLS nas tabelas de storage
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY;

-- Policy: service_role pode tudo em objects
CREATE POLICY "Service role full access" ON storage.objects
  FOR ALL USING (
    (SELECT auth.role()) = 'service_role'
  );

-- Policy: service_role pode tudo em buckets
CREATE POLICY "Service role full access" ON storage.buckets
  FOR ALL USING (
    (SELECT auth.role()) = 'service_role'
  );

-- Policy: authenticated users podem acessar seus uploads
CREATE POLICY "Authenticated upload" ON storage.objects
  FOR INSERT WITH CHECK (
    (SELECT auth.role()) = 'authenticated'
  );

CREATE POLICY "Authenticated read own" ON storage.objects
  FOR SELECT USING (
    (SELECT auth.role()) IN ('authenticated', 'anon')
    AND bucket_id IN (
      SELECT id FROM storage.buckets WHERE public = true
    )
  );
```

### Verificação

```bash
# Via CLI
raijin-server supabase-security status

# Manual
kubectl exec postgres-0 -n supabase -- psql -U postgres -c \
  "SELECT schemaname, tablename, rowsecurity FROM pg_tables 
   WHERE schemaname IN ('public','storage') ORDER BY schemaname, tablename;"
```

> **Importante**: Tabelas que você criar no schema `public` devem **sempre** ter RLS habilitado + policies adequadas. Sem isso, a `anon_key` dá acesso total.

---

## 3. Kong — ClusterIP em vez de LoadBalancer

### Problema

Kong configurado como `LoadBalancer` recebe IP externo (192.168.1.103), permitindo acesso HTTP direto sem TLS/Traefik.

### Solução

```yaml
# ANTES
spec:
  type: LoadBalancer  # ← acessível diretamente

# DEPOIS
spec:
  type: ClusterIP     # ← acesso apenas via Traefik
```

Todo tráfego externo passa obrigatoriamente pelo Traefik Ingress (TLS enforced).

---

## 4. Rate Limiting

### Problema

Sem rate limiting, o Supabase é vulnerável a:
- Brute force de login
- DDoS / abuso de API
- Scraping massivo de dados
- Enumeração de email via signup

### Solução

Rate limiting por serviço no Kong:

| Serviço | Limite | Justificativa |
|---------|--------|---------------|
| Auth    | 30 req/min | Signup/login são operações pesadas |
| REST    | 300 req/min | API principal, uso moderado |
| Storage | 60 req/min | Upload/download são pesados em I/O |
| Realtime | 60 req/min | WebSocket handshake |

```yaml
plugins:
  - name: rate-limiting
    config:
      minute: 30
      policy: local
      fault_tolerant: true
      hide_client_headers: false
```

---

## 5. MinIO — Acesso Interno

### Problema

MinIO exposto via `NodePort` (30900/30901) — console e API acessíveis na rede local.

### Solução

Converter MinIO de `NodePort` para `ClusterIP`. Apenas o Storage API do Supabase precisa acessar MinIO internamente.

---

## 6. Security Headers (Traefik)

### Solução

Middleware Traefik com headers de segurança:

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: security-headers
  namespace: supabase
spec:
  headers:
    stsSeconds: 31536000
    stsIncludeSubdomains: true
    stsPreload: true
    contentTypeNosniff: true
    frameDeny: true
    browserXssFilter: true
    referrerPolicy: "strict-origin-when-cross-origin"
    customResponseHeaders:
      X-Powered-By: ""
      Server: ""
```

---

## 7. GoTrue Hardening

### Configurações de segurança aplicadas

| Variável | Valor | Descrição |
|----------|-------|-----------|
| `GOTRUE_RATE_LIMIT_HEADER` | `X-Forwarded-For` | Rate limit por IP real |
| `GOTRUE_RATE_LIMIT_EMAIL_SENT` | `5` | Max emails/hora |
| `GOTRUE_URI_ALLOW_LIST` | domínios explícitos | Redirect URLs permitidas |
| `GOTRUE_MAILER_AUTOCONFIRM` | `true` | Mantido para dev/PoC |

---

## 8. Network Policies

### Políticas aplicadas

```
Internet → Traefik (TLS) → Kong → Services → PostgreSQL
                                       ↓
                                     MinIO
```

| Policy | Regra |
|--------|-------|
| `postgres-allow-supabase` | PostgreSQL aceita apenas pods do namespace supabase |
| `supabase-services-allow-kong` | Serviços aceitam tráfego apenas do Kong |
| `kong-allow-ingress` | Kong aceita apenas do Traefik Ingress |
| `storage-allow-minio` | Storage pode acessar MinIO no namespace minio |
| `supabase-allow-dns` | DNS + comunicação interna permitidos |

---

## Gerenciamento de Aplicações (CLI)

### Registrar nova aplicação

Para permitir que outra aplicação do cluster use o Supabase:

```bash
# Adicionar aplicação com domínio CORS
raijin-server supabase-security app-add \
  --name "meu-mvp" \
  --domain "https://meu-mvp.cryptidnest.com"

# Adicionar aplicação Lovable
raijin-server supabase-security app-add \
  --name "lovable-app" \
  --domain "https://meu-app.lovable.app"
```

Isso adiciona o domínio ao CORS do Kong e registra a aplicação.

### Remover aplicação

```bash
raijin-server supabase-security app-remove --name "meu-mvp"
```

### Listar aplicações registradas

```bash
raijin-server supabase-security app-list
```

### Fluxo para PoCs e MVPs

1. Registrar app: `raijin-server supabase-security app-add --name "poc-xyz" --domain "https://poc.cryptidnest.com"`
2. Usar credenciais do Supabase no app (mesma URL + Anon Key)
3. Criar tabelas com RLS no schema `public`
4. Quando terminar: `raijin-server supabase-security app-remove --name "poc-xyz"`

---

## Checklist de Segurança

```bash
# Verificar status completo
raijin-server supabase-security status
```

| Item | Status | Como verificar |
|------|--------|---------------|
| CORS restrito | ✅ | `cors-list` |
| RLS habilitado (storage) | ✅ | `status` |
| Kong ClusterIP | ✅ | `kubectl get svc supabase-kong -n supabase` |
| Rate Limiting | ✅ | `status` |
| MinIO interno | ✅ | `kubectl get svc -n minio` |
| Security Headers | ✅ | `curl -I https://supabase.cryptidnest.com` |
| GoTrue hardened | ✅ | `status` |
| Network Policies | ✅ | `kubectl get networkpolicies -n supabase` |

---

## Diagrama de Segurança

```
┌─────────────────────────────────────────────────────────────┐
│                        INTERNET                             │
│  App Lovable  │  PoC/MVP Apps  │  Blocked Origins (❌)      │
└───────┬───────┴────────┬───────┴────────────────────────────┘
        │                │
        ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  Traefik Ingress                                            │
│  ├─ TLS (Let's Encrypt)                                     │
│  ├─ Security Headers (HSTS, X-Frame-Options, CSP)           │
│  └─ HTTPS only                                              │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│  Kong Gateway (ClusterIP only)                              │
│  ├─ CORS: allowlist de domínios                             │
│  ├─ Rate Limiting: 30-300 req/min por serviço               │
│  └─ Routing: auth/rest/storage/realtime                     │
└───┬──────────┬──────────┬──────────┬────────────────────────┘
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌────▼────┐ ┌──▼──────┐
│GoTrue │ │PgREST │ │Storage  │ │Realtime │
│ Auth  │ │ REST  │ │ S3 API  │ │   WS    │
└───┬───┘ └───┬───┘ └──┬──┬──┘ └────┬────┘
    │         │        │  │         │         Network Policies
    └─────────┴────────┘  │         │         isolam cada camada
                │         │         │
        ┌───────▼─────┐   │         │
        │ PostgreSQL  │   │         │
        │ RLS ativo   │   │         │
        │ search_path │   │         │
        └─────────────┘   │         │
                   ┌──────▼──────┐  │
                   │    MinIO    │  │
                   │ ClusterIP   │  │
                   │ (interno)   │  │
                   └─────────────┘  │
```

---

> **Dúvidas?** Execute `raijin-server supabase-security status` para um relatório completo.
