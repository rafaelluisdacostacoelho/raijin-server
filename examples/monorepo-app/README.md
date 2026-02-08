# Monorepo App — Template

Template completo e funcional para projetos monorepo com múltiplos backends e frontends, pronto para produção com segurança, CI/CD e GitOps.

## Arquitetura

```
monorepo-app/
├── backends/
│   ├── api-go/          ← API principal (Go 1.24+ / stdlib net/http)
│   ├── api-python/      ← API auxiliar (Python 3.14+ / FastAPI) — dummy
│   └── api-dotnet/      ← API auxiliar (C# .NET 9 Minimal API) — dummy
├── frontends/
│   ├── meu-app-web/     ← SPA principal (React 19 + Vite 6 + Tailwind 4)
│   ├── meu-app-admin/   ← Painel admin (Angular 19) — dummy
│   ├── meu-app-apk/     ← App Android — placeholder
│   └── meu-app-ios/     ← App iOS — placeholder
├── kubernetes/
│   ├── base/            ← Manifests base (Kustomize)
│   └── overlays/
│       ├── tst/         ← Overlay teste (1 réplica, auto-sync)
│       └── prd/         ← Overlay produção (3 réplicas, HPA, PDB)
├── .github/workflows/
│   ├── ci-tst.yml       ← Pipeline TST (push develop)
│   └── ci-prd.yml       ← Pipeline PRD (tag v*)
├── scripts/
│   ├── setup.sh         ← Setup inicial do ambiente
│   ├── vault-setup.sh   ← Configuração do Vault
│   └── security-check.sh ← Checklist de segurança
├── docker-compose.yml   ← Dev environment completo
└── Makefile             ← Comandos centralizados
```

## Quick Start

```bash
# 1. Clone e configure
git clone <repo> && cd monorepo-app
chmod +x scripts/*.sh
./scripts/setup.sh

# 2. Subir tudo via Docker
make dev

# 3. Acessar
#   Frontend:  http://localhost:5173
#   API Go:    http://localhost:8080
#   MailHog:   http://localhost:8025
#   Adminer:   http://localhost:8181

# 4. Login demo
#   Email: admin@example.com
#   Senha: admin123
```

## Stack Tecnológica

| Camada      | Tecnologia                         | Versão   |
|-------------|-------------------------------------|----------|
| API         | Go + stdlib `net/http`              | 1.24+    |
| API aux.    | Python + FastAPI                    | 3.14+    |
| API aux.    | C# + .NET Minimal API              | 9.0      |
| Frontend    | React + Vite + Tailwind + Zustand   | 19 / 6 / 4 / 5 |
| Admin       | Angular                             | 19       |
| Banco       | PostgreSQL                          | 17       |
| Cache       | Redis                               | 7        |
| Container   | Docker + Compose                    | 27+      |
| Orquestração| Kubernetes + Kustomize              | 1.31+    |
| GitOps      | ArgoCD                              | 2.13+    |
| Registry    | Harbor                              | 2.12+    |
| Secrets     | Vault + ExternalSecrets Operator    | 1.15+ / 0.12+ |
| CI/CD       | GitHub Actions                      | -        |

---

## Backends

### API Go (Principal — Funcional)

API completa com autenticação, autorização e segurança embutida. Usa **somente stdlib** (`net/http` com Go 1.22+ routing) + `golang.org/x/crypto/bcrypt`.

**Endpoints:**

| Método | Rota                     | Auth  | Descrição                |
|--------|--------------------------|-------|--------------------------|
| GET    | `/health`                | Não   | Health check             |
| GET    | `/ready`                 | Não   | Readiness (deps)         |
| POST   | `/api/v1/auth/register`  | Não   | Registrar usuário        |
| POST   | `/api/v1/auth/login`     | Não   | Login (retorna JWT)      |
| POST   | `/api/v1/auth/refresh`   | JWT   | Renovar token            |
| GET    | `/api/v1/users/me`       | JWT   | Perfil do usuário        |
| GET    | `/api/v1/users`          | Admin | Listar usuários          |

**Features implementadas:**
- JWT HS256 com tokens em memória (nunca localStorage)
- Bcrypt para hashing de senhas
- CSRF tokens em rotas state-changing (POST/PUT/DELETE)
- Rate limiting por IP (in-memory, trocar por Redis em produção)
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- CORS configurável por variável de ambiente
- User store in-memory (trocar por PostgreSQL/pgx em produção)

**Variáveis de ambiente:**

| Variável        | Default                         | Descrição               |
|-----------------|----------------------------------|--------------------------|
| `PORT`          | `8080`                           | Porta do servidor        |
| `JWT_SECRET`    | `change-me-in-production...`     | Chave HMAC para JWT      |
| `ALLOWED_ORIGINS` | `http://localhost:5173`        | Origins permitidas (CSV) |
| `DATABASE_URL`  | `postgres://app:...`             | Connection string        |
| `REDIS_URL`     | `redis://localhost:6379/0`       | Redis URL                |
| `ENV`           | `development`                    | Ambiente                 |

**Desenvolvimento local:**

```bash
# Via Docker (recomendado)
make dev

# Local direto
make dev-api   # Sobe postgres+redis via Docker, API Go local
```

### API Python (Dummy)

FastAPI com endpoints CRUD básicos. Serve como ponto de partida para microserviços Python.

```bash
cd backends/api-python
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8081
```

### API .NET (Dummy)

.NET 9 Minimal API. Serve como ponto de partida para microserviços C#.

```bash
cd backends/api-dotnet
dotnet run
```

---

## Frontends

### meu-app-web (React — Funcional)

SPA completa com login, registro e dashboard. Conecta-se à API Go com segurança.

**Páginas:**
- `/login` — Formulário de login com demo credentials
- `/register` — Formulário de registro com validação
- `/dashboard` — Dashboard com info do usuário, status da API e indicadores de segurança

**Segurança do frontend:**
- Tokens JWT armazenados **apenas em memória** (Zustand) — nunca localStorage
- CSRF token enviado em header `X-CSRF-Token` em toda requisição de escrita
- DOMPurify para sanitização de dados vindos da API (prevenção XSS)
- Meta tags CSP no `index.html`
- Nginx reverse proxy em produção (same-origin = sem CORS)
- Auto-refresh de tokens antes de expirar

**Desenvolvimento:**

```bash
# Via Docker
make dev

# Local (com proxy para API)
cd frontends/meu-app-web
npm install && npm run dev
# Proxy automático: /api → http://localhost:8080 (vite.config.ts)
```

### meu-app-admin (Angular — Dummy)

Painel admin Angular 19 com standalone components. Usar como ponto de partida.

### meu-app-apk / meu-app-ios (Placeholders)

Estrutura mínima para apps mobile. Veja os READMEs dentro de cada pasta para opções de framework (React Native, Flutter, Kotlin, Swift).

---

## Segurança

### Modelo Same-Origin (Produção)

```
Navegador → nginx (:443)
               ├── /           → SPA (arquivos estáticos)
               └── /api/       → proxy_pass api-go:8080
```

O nginx faz proxy reverso para a API, eliminando CORS em produção. Ambos os domínios compartilham a mesma origem. Isso é a defesa mais eficaz contra CSRF e simplifica a configuração.

### Camadas de Proteção

| Camada             | Implementação                               | Onde              |
|--------------------|---------------------------------------------|-------------------|
| **CORS**           | Whitelist de origins via env var             | API Go            |
| **CSRF**           | Token gerado no login, validado em writes   | API Go + Frontend |
| **XSS**            | DOMPurify, CSP headers, no-inline scripts   | Frontend + Nginx  |
| **Auth**           | JWT HS256, tokens em memória, refresh flow  | API Go + Zustand  |
| **Senhas**         | bcrypt com cost factor 12                    | API Go            |
| **Rate Limiting**  | Por IP, 100 req/min (in-memory)             | API Go            |
| **Headers**        | HSTS, CSP, X-Frame-Options, X-XSS, CORP    | API Go + Nginx    |
| **Containers**     | Non-root, multi-stage, alpine               | Dockerfiles       |
| **Secrets**        | Vault + ExternalSecrets (zero secrets em YAML) | Kubernetes      |
| **SAST**           | Semgrep no CI                                | GitHub Actions    |
| **Container Scan** | Trivy no pipeline PRD                        | GitHub Actions    |

### Checklist de Segurança

```bash
./scripts/security-check.sh
```

---

## Docker Compose

```bash
make dev          # Subir todos os serviços
make stop         # Parar
make logs         # Ver logs
make clean        # Remover containers + volumes
```

**Serviços:**

| Serviço        | Porta  | Descrição                   |
|----------------|--------|-----------------------------|
| meu-app-web    | 5173   | Frontend React              |
| api-go         | 8080   | API Go (principal)          |
| api-python     | 8081   | API Python (dummy)          |
| api-dotnet     | 8082   | API .NET (dummy)            |
| postgres       | 5432   | PostgreSQL 17               |
| redis          | 6379   | Redis 7                     |
| mailhog        | 8025   | SMTP fake (dev)             |
| adminer        | 8181   | DB admin UI                 |

---

## Kubernetes

### Estrutura Kustomize

```
kubernetes/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── ingress.yaml           ← 4 hosts (web, api-go, api-python, api-dotnet)
│   ├── externalsecrets.yaml   ← 3 secrets do Vault
│   ├── meu-app-web.yaml       ← Deployment + Service
│   ├── api-go.yaml
│   ├── api-python.yaml
│   ├── api-dotnet.yaml
│   ├── database.yaml           ← StatefulSet PostgreSQL
│   └── redis.yaml               ← Deployment Redis
├── overlays/
│   ├── tst/                     ← 1 réplica, tags develop
│   └── prd/                     ← 3 réplicas, HPA (4), PDB (5)
└── argocd-apps.yaml             ← 2 Applications + AppProject
```

### Deploy Manual

```bash
# TST
make deploy-tst
# ou
kubectl apply -k kubernetes/overlays/tst

# PRD
make deploy-prd
# ou
kubectl apply -k kubernetes/overlays/prd
```

### ArgoCD (GitOps)

```bash
kubectl apply -f kubernetes/argocd-apps.yaml
```

- **TST**: Auto-sync habilitado, auto-prune
- **PRD**: Sync manual, sem auto-prune, sem self-heal

### Vault + ExternalSecrets

```bash
# Configurar Vault para TST
./scripts/vault-setup.sh meu-app-tst tst

# Configurar Vault para PRD
./scripts/vault-setup.sh meu-app-prd prd
```

---

## CI/CD

### Pipeline TST (`ci-tst.yml`)

Ativado em: push para `develop` com mudanças em paths específicos.

```
Push develop → Semgrep (non-blocking)
             → Build & Test (por serviço, com path filter)
             → Push image para Harbor (:develop-SHA)
             → Update kustomization.yaml
             → ArgoCD auto-sync
             → Slack notification
```

### Pipeline PRD (`ci-prd.yml`)

Ativado em: push de tags `v*`.

```
Tag v* → Semgrep + OWASP (BLOCKING)
       → Build & Test (por serviço)
       → Trivy scan (bloqueia CRITICAL)
       → Push image (:v1.2.3 + :stable)
       → Provenance + SBOM
       → GitHub Release
       → Slack: "approve ArgoCD sync"
```

### Variáveis Necessárias (GitHub Secrets)

| Secret                  | Descrição                          |
|-------------------------|------------------------------------|
| `HARBOR_REGISTRY`       | URL do Harbor (harbor.asgard.local)|
| `HARBOR_USERNAME`       | Usuário Harbor                     |
| `HARBOR_PASSWORD`       | Senha Harbor                       |
| `HARBOR_PROJECT`        | Projeto no Harbor (tst/prd)        |
| `ARGOCD_SERVER`         | URL do ArgoCD                      |
| `ARGOCD_AUTH_TOKEN`     | Token do ArgoCD                    |
| `SLACK_WEBHOOK`         | Webhook do Slack                   |
| `SEMGREP_APP_TOKEN`     | Token Semgrep (opcional)           |

---

## Personalização

### Criar Novo Backend

1. Copiar um dos dummies (`api-python` ou `api-dotnet`)
2. Renomear pasta para `api-<nome>`
3. Adicionar no `docker-compose.yml`
4. Adicionar job no `ci-tst.yml` e `ci-prd.yml`
5. Criar manifests em `kubernetes/base/<nome>.yaml`
6. Adicionar em `kubernetes/base/kustomization.yaml`

### Criar Novo Frontend

1. Copiar `meu-app-admin` como base
2. Renomear pasta
3. Adicionar no `docker-compose.yml`
4. Seguir mesmo padrão de CI/CD e Kubernetes

### Migrar In-Memory → PostgreSQL

O arquivo `backends/api-go/cmd/server/main.go` usa um `Store` in-memory para desenvolvimento. Para migrar:

1. Adicionar `github.com/jackc/pgx/v5` no `go.mod`
2. Substituir a struct `Store` por conexão pgx
3. Rodar migrations (ferramenta sugerida: `golang-migrate/migrate`)
4. Atualizar `DATABASE_URL` no ExternalSecret

### Migrar Rate Limiter → Redis

O rate limiter usa `sync.Map` in-memory. Para migrar:

1. Adicionar `github.com/redis/go-redis/v9` no `go.mod`
2. Substituir `RateLimiter` por implementação Redis
3. Atualizar `REDIS_URL` no ExternalSecret

---

## Comandos

```bash
make help           # Ver todos os comandos disponíveis
make dev            # Subir todos os serviços
make dev-web        # Apenas frontend (local + hot reload)
make dev-api        # Apenas API Go (local) + deps Docker
make build-all      # Build de todas as imagens
make test-all       # Rodar todos os testes
make lint           # Rodar todos os linters
make deploy-tst     # Deploy para TST
make deploy-prd     # Deploy para PRD (com confirmação)
make clean          # Limpar containers e volumes
make db-shell       # Shell psql no PostgreSQL
```

---

## Licença

Uso interno. Customize conforme necessário.
