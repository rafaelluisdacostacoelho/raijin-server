# 🚀 Workflow: Publicar Apps no Raijin-Server

## Visão Geral

```
┌────────────────────────────────────────────────────────────┐
│                  INFRAESTRUTURA EXISTENTE                  │
│                                                            │
│  Raijin-Server já configurado e rodando                    │
│  ------------------------------------------------          │
│  • Kubernetes (K3s)                                        │
│  • Argo CD (GitOps)                                        │
│  • Harbor (Registry privado)                               │
│  • Vault (Secrets)                                         │
│  • Traefik (Ingress + SSL)                                 │
│  • Prometheus + Grafana (Monitoring)                       │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│              PUBLICAR NOVO APP (VOCÊ ESTÁ AQUI)            │
│  Website, API, SPA, Full-stack...                          │
└────────────────────────────────────────────────────────────┘
```

---

## 🎯 Objetivo

**Publicar novos aplicativos** na infraestrutura Kubernetes já configurada, com:
- ✅ Build automático (CI)
- ✅ Deploy automático (CD)
- ✅ Acessível na internet com domínio próprio
- ✅ HTTPS automático
- ✅ Secrets seguros
- ✅ Monitoring ativo

---

## 📊 Workflow Completo

### Fase 1: Desenvolvimento Local

```bash
# Seu app em desenvolvimento
myapp/
├── frontend/       # React, Vue, Next.js...
├── backend/        # Go, Python, Node...
└── docker-compose.yml  # Testar local
```

**Teste local**:
```bash
docker-compose up
# http://localhost:3000
```

---

### Fase 2: Configurar CI/CD (Uma Única Vez)

Use um dos guias para configurar:

**Opção A - Com Copilot** (Recomendado para iniciantes):
1. Abra [COPILOT_PROMPT.md](COPILOT_PROMPT.md)
2. Cole no Copilot com detalhes do seu app
3. Copilot gera toda configuração

**Opção B - Manual Rápido** (Para experientes):
1. Abra [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)
2. Copie templates necessários
3. Customize para seu app

**Opção C - Exemplo Prático** (Para aprender):
1. Siga [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) passo a passo
2. Adapte para seu projeto

**O que será criado**:
```
myapp/
├── .github/workflows/
│   ├── ci-tst.yml          # Pipeline TST
│   └── ci-prd.yml          # Pipeline PRD
├── kubernetes/
│   ├── base/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   └── externalsecrets.yaml
│   └── overlays/
│       ├── tst/
│       └── prd/
├── Dockerfile              # Multi-stage otimizado
└── README.md
```

---

### Fase 3: Push para GitHub

```bash
git init
git add .
git commit -m "feat: initial setup with CI/CD"
git branch -M main
git remote add origin https://github.com/you/myapp.git
git push -u origin main

# Criar branch develop para TST
git checkout -b develop
git push -u origin develop
```

---

### Fase 4: Pipeline Automático (Acontece Sozinho!)

#### Push em `develop` → Deploy TST Automático

```
1. Developer: git push origin develop
                    ↓
2. GitHub Actions CI:
   • Checkout código
   • Build Docker image (multi-stage)
   • Scan segurança (Semgrep + Trivy)
   • Push para Harbor: tst/myapp:dev-abc123
   • Update Kustomize com novo tag
                    ↓
3. Argo CD detecta mudança:
   • Sync automático (TST tem auto-sync)
   • Apply manifests no Kubernetes
   • Health check
                    ↓
4. App rodando em TST:
   https://myapp-tst.local ✅
```

#### Push em `main` → Deploy PRD Manual

```
1. Developer: git push origin main
                    ↓
2. GitHub Actions CI:
   • Build + Scan (stricter em PRD)
   • Push para Harbor: prd/myapp:v1.0.0
                    ↓
3. Argo CD detecta mudança:
   • AGUARDA APROVAÇÃO MANUAL
   • DevOps aprova no ArgoCD UI
   • Deploy em PRD
                    ↓
4. App rodando em PRD:
   https://myapp.com ✅ (Internet pública!)
```

---

## 🔄 Workflow Diário

Depois da configuração inicial, seu workflow será:

```bash
# 1. Desenvolver feature
git checkout develop
# ... código ...

# 2. Commit e push
git add .
git commit -m "feat: nova funcionalidade"
git push origin develop

# 3. Aguardar pipeline (2-5 min)
# GitHub Actions → Build → Harbor → ArgoCD

# 4. Testar em TST
https://myapp-tst.local

# 5. Se OK, mergear para main
git checkout main
git merge develop
git push origin main

# 6. Aprovar deploy em PRD (ArgoCD UI)
# App atualizado em produção!
```

---

## 🏗️ Arquitetura de Publicação

```
┌─────────────────────────────────────────────────────────────┐
│                         INTERNET                            │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
                    ┌────▼────┐
                    │ Traefik │ (Ingress + SSL)
                    │ Ingress │
                    └────┬────┘
                         │
              ┌──────────┴───────────┐
              │                      │
        ┌─────▼─────┐          ┌─────▼─────┐
        │ Frontend  │          │  Backend  │
        │  (Nginx)  │          │   (API)   │
        │   :80     │─────────>│  :8080    │
        └───────────┘          └─────┬─────┘
                                     │
                    ┌────────────────┼───────────────┐
                    │                │               │
              ┌─────▼──────┐   ┌─────▼─────┐   ┌─────▼─────┐
              │ PostgreSQL │   │   Redis   │   │   Vault   │
              │(StatefulSet│   │  (Cache)  │   │ (Secrets) │
              │    +PVC)   │   │           │   │           │
              └────────────┘   └───────────┘   └───────────┘

┌────────────────────────────────────────────────────────────┐
│                     MONITORAMENTO                          │
│  Prometheus scrape → Grafana dashboards                    │
│  Loki logs → Grafana explore                               │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                     BUILD & REGISTRY                       │
│  GitHub Actions → Docker Build → Harbor Registry           │
│                   (Harbor scan vulnerabilities)            │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                        GITOPS                              │
│  Git Repo → ArgoCD sync → Kubernetes Apply                 │
│  (Single source of truth)                                  │
└────────────────────────────────────────────────────────────┘
```

---

## 📋 Checklist: Publicar Novo App

### Pré-requisitos
- [ ] Infraestrutura raijin-server configurada
- [ ] Código do app pronto (rodando localmente)
- [ ] Repositório GitHub criado
- [ ] Domínio configurado (ou usar subdomínio do servidor)

### Configuração (Uma vez por app)
- [ ] Escolher guia (COPILOT_PROMPT, QUICK_START ou EXAMPLE)
- [ ] Criar Dockerfiles
- [ ] Criar Kubernetes manifests
- [ ] Configurar pipeline CI/CD (.github/workflows/)
- [ ] Configurar secrets no Vault
- [ ] Criar Argo CD Application
- [ ] Testar deploy em TST

### Publicação
- [ ] Push código para GitHub
- [ ] Pipeline executa automaticamente
- [ ] Verificar deploy em TST: https://app-tst.local
- [ ] Testar funcionalidades
- [ ] Mergear para main
- [ ] Aprovar deploy em PRD (ArgoCD UI)
- [ ] Verificar em produção: https://app.com ✅

---

## 🎓 Aprendizado Progressivo

### Nível 1: Primeira Publicação (3-5h)
- Siga [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) completo
- Use [COPILOT_PROMPT.md](COPILOT_PROMPT.md) para gerar config
- Entenda cada etapa

### Nível 2: Publicações Seguintes (1-2h)
- Use [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)
- Reaproveite configs anteriores
- Customize rapidamente

### Nível 3: Automação (30min por app)
- Use [AGENT_GUIDE.md](AGENT_GUIDE.md)
- Crie scripts reutilizáveis
- Publicação em massa

---

## 💡 Dicas Importantes

### Ambientes
- **TST** (`develop` branch): Deploy automático, testes, staging
- **PRD** (`main` branch): Deploy manual, produção, internet pública

### Secrets
❌ **NUNCA** commite secrets no Git!
✅ **SEMPRE** use Vault + External Secrets

### Domínios
- TST: Use `.local` (interno) ou `tst-app.seudominio.com`
- PRD: Use domínio real `app.seudominio.com`

### Monitoring
- Sempre adicione ServiceMonitor (Prometheus)
- Configure dashboards Grafana
- Configure alertas críticos

### Backups
- PostgreSQL: Configure Velero backup
- Volumes: PVC com snapshot
- Git: Sempre é seu backup de código

---

## 🆘 Troubleshooting Rápido

### Pipeline falha
```bash
# Ver logs GitHub Actions
gh run view --log

# Ou na UI
open https://github.com/you/myapp/actions
```

### ArgoCD não sincroniza
```bash
# Ver status
kubectl get application myapp-tst -n argocd

# Forçar sync
argocd app sync myapp-tst --force
```

### App não responde
```bash
# Ver pods
kubectl get pods -n myapp-tst

# Ver logs
kubectl logs -n myapp-tst -l app=backend --tail=100

# Descrever pod
kubectl describe pod <pod-name> -n myapp-tst
```

### Secrets não aparecem
```bash
# Ver ExternalSecret
kubectl get externalsecret -n myapp-tst

# Descrever
kubectl describe externalsecret myapp-secrets -n myapp-tst

# Verificar Vault
kubectl exec -n vault vault-0 -- vault kv get secret/myapp/database
```

---

## 🔗 Links Úteis

| Ferramenta | URL | Uso |
|------------|-----|-----|
| ArgoCD UI | https://argocd.local | Aprovar deploys PRD |
| Harbor | https://harbor.local | Ver imagens Docker |
| Grafana | https://grafana.local | Dashboards e logs |
| Prometheus | (port-forward 9090) | Queries de métricas |

---

## 📚 Próximos Passos

Depois de publicar seu primeiro app:

1. **Segundo app**: Muito mais rápido! (1-2h)
2. **Customize monitoring**: Dashboards específicos
3. **Configure alertas**: Slack/Email quando falhas
4. **Optimize**: Ajuste replicas, resources, HPA
5. **Backup**: Configure Velero para disaster recovery

---

**Pronto para começar?** 

👉 Vá para [INDEX.md](INDEX.md) e escolha seu guia!

ou

👉 Veja exemplo prático em [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md)
