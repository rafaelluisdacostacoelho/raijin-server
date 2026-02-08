# 🚀 Publicar Novos Apps - Índice Navegável

```
┌──────────────────────────────────────────────────────┐
│  PUBLICAR NOVOS APLICATIVOS NO KUBERNETES PRODUTIVO  │
│  Via CI/CD automático com GitHub + ArgoCD            │
│  Infraestrutura raijin-server já configurada!        │ 
└──────────────────────────────────────────────────────┘
```

---

## 💡 Contexto

Você já tem a **infraestrutura raijin-server configurada e rodando** (Kubernetes + ArgoCD + Harbor + Vault + Traefik).

Agora você quer **publicar novos aplicativos** (websites, APIs, SPAs, etc.) nessa infraestrutura:
- Código no GitHub
- Build automático via CI/CD
- Deploy automático no Kubernetes
- Exposto na internet via Traefik

---

## 🎯 Escolha Rápida (Início Aqui!)

### Tenho um novo projeto (website/API) para publicar
👉 **[COPILOT_PROMPT.md](COPILOT_PROMPT.md)** → Use com Copilot/Claude para gerar configuração  
👉 **[EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md)** → Exemplo prático completo

### Quero publicar rapidamente (já sei Kubernetes)
👉 **[QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)** → Templates diretos

### Quero automatizar publicação de múltiplos apps
👉 **[AGENT_GUIDE.md](AGENT_GUIDE.md)** → Scripts de automação

---

## 📚 Todos os Documentos

### 📘 0. WORKFLOW.md ⭐ COMECE AQUI
**Visão geral** do workflow completo de publicação

**Contém**:
- Workflow passo a passo visual
- Do desenvolvimento até produção
- Arquitetura de publicação
- Checklist completo
- Troubleshooting rápido

### 🌐 1. DOMAIN_SETUP.md ⚙️ CONFIGURAÇÃO DNS
**Guia completo de DNS e exposição de serviços**

**Contém**:
- Configuração DNS no Cloudflare (cryptidnest.com)
- Traefik Ingress setup
- cert-manager TLS automático
- Template para expor novos serviços
- Troubleshooting DNS/TLS
- Exemplos práticos (Supabase, Harbor, Argo CD)

**Leia primeiro**: ✅ Sim, para entender o processo completo

📄 **[Abrir WORKFLOW.md](WORKFLOW.md)**

---

### 📘 1. INDEX.md (Você está aqui!)
**Visão geral** de todos os documentos e como escolher

**Contém**:
- Descrição de cada documento
- Tabela de decisão
- Fluxos recomendados
- FAQ

**Leia primeiro**: ✅ Sim, se não souber por onde começar

---

### 📗 2. COPILOT_PROMPT.md
**Prompt detalhado** para assistentes de IA (Copilot, Claude, ChatGPT)

**Para quem**:
- ✅ Tem um novo app (website/API) para publicar
- ✅ Quer configurar CI/CD automaticamente
- ✅ Prefere assistência de IA
- ✅ Infraestrutura raijin-server já configurada

**O que você ganha**:
- Configuração completa de CI/CD para seu app
- Instruções passo a passo detalhadas
- Dockerfiles otimizados
- Kubernetes manifests prontos
- Pipeline GitHub Actions ou Argo Workflows
- Deploy automático em produção
- Checklist de validação

**Tempo estimado**: 30min para ler + 2-4h para implementar (com IA)

**Próximo passo**: Copie o prompt → Cole no Copilot → Customize

📄 **[Abrir COPILOT_PROMPT.md](COPILOT_PROMPT.md)**

---

### 📕 3. AGENT_GUIDE.md
**Guia técnico** com comandos shell executáveis

**Para quem**:
- ✅ DevOps publicando múltiplos apps
- ✅ Quer automação completa
- ✅ Prefere linha de comando
- ✅ Criar scripts de publicação reutilizáveis

**O que você ganha**:
- Comandos shell prontos para executar
- Scripts de publicação automatizada
- Troubleshooting técnico
- Checklist automatizado
- Processo replicável para qualquer app

**Tempo estimado**: 2-3h (primeira vez), 30min (apps seguintes)

**Próximo passo**: Siga fase por fase ou extraia comandos

📄 **[Abrir AGENT_GUIDE.md](AGENT_GUIDE.md)**

---

### 📙 4. QUICK_START_TEMPLATE.md
**Templates mínimos** para publicação rápida

**Para quem**:
- ✅ Experiente com Kubernetes
- ✅ Já publicou apps antes
- ✅ Quer publicar rápido
- ✅ Referência rápida

**O que você ganha**:
- Templates prontos (Dockerfile, Kustomize, Pipeline)
- Variáveis de configuração
- One-liner commands
- Publicação em produção em 1-2h
- Troubleshooting rápido

**Tempo estimado**: 1-2h (app simples), 30min (se souber o que está fazendo)

**Próximo passo**: Copie templates → Customize → Deploy

📄 **[Abrir QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)**

---

### 📔 5. EXAMPLE_ECOMMERCE.md ⭐
**Exemplo prático completo** de publicação

**Para quem**:
- ✅ Todos os níveis
- ✅ Primeira vez publicando app no raijin-server
- ✅ Quer ver exemplo real completo
- ✅ Validar cada etapa

**O que você ganha**:
- Exemplo real: E-commerce Platform (Next.js + Go)
- Do código até app rodando em produção na internet
- Outputs esperados de cada comando
- Validações em cada etapa
- Troubleshooting de problemas reais
- URL final funcionando: https://shop.example.com

**Tempo estimado**: 3-5h (primeira vez), 1-2h (apps seguintes)

**Próximo passo**: Siga linha por linha, adaptando ao seu projeto

📄 **[Abrir EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md)**

---

## 🛤️ Fluxos Recomendados

### Fluxo 1: Iniciante Total
```
1. Leia WORKFLOW.md para entender o processo ← COMECE AQUI!
2. Leia INDEX.md (este arquivo)
3. Leia COPILOT_PROMPT.md para entender contexto
4. Siga EXAMPLE_ECOMMERCE.md passo a passo
5. Use COPILOT_PROMPT.md com Copilot para seu app
6. Consulte AGENT_GUIDE.md para troubleshooting
```

### Fluxo 2: Desenvolvedor Experiente
```
1. Leia WORKFLOW.md (visão geral) ← COMECE AQUI!
2. Leia INDEX.md (este arquivo)
3. Abra QUICK_START_TEMPLATE.md
4. Copie templates necessários
5. Customize para seu app
6. Deploy em 1-2h
```

### Fluxo 3: DevOps/Automação
```
1. Leia WORKFLOW.md (arquitetura) ← COMECE AQUI!
2. Leia INDEX.md (este arquivo)
3. Abra AGENT_GUIDE.md
4. Extraia comandos shell
5. Crie script de publicação
6. Execute checklist automatizado
```

### Fluxo 4: Aprendizado
```
1. Leia WORKFLOW.md (visão completa) ← COMECE AQUI!
2. Leia INDEX.md (este arquivo)
3. Leia COPILOT_PROMPT.md (contexto completo)
4. Siga EXAMPLE_ECOMMERCE.md (prática guiada)
5. Use AGENT_GUIDE.md (comandos técnicos)
6. Refine com QUICK_START_TEMPLATE.md
```

---

## 📊 Comparação Rápida

| Aspecto | COPILOT_PROMPT | AGENT_GUIDE | QUICK_START | EXAMPLE |
|---------|----------------|-------------|-------------|---------|
| **Nível** | Iniciante-Intermediário | Intermediário-Avançado | Avançado | Todos |
| **Formato** | Narrativo + Exemplos | Shell commands | Templates | Tutorial |
| **Tempo** | 3-5h | 2-4h | 1-2h | 4-6h |
| **Automação** | ❌ Manual (com IA) | ✅ Scriptável | ⚠️ Parcial | ❌ Manual |
| **Explicações** | ✅✅✅ Detalhadas | ✅✅ Técnicas | ✅ Mínimas | ✅✅✅ Passo a passo |
| **Código completo** | ✅ Sim | ⚠️ Comandos | ⚠️ Templates | ✅ Sim + Outputs |
| **Ideal para** | Primeira vez | Scripts | MVP rápido | Aprendizado |

---

## ❓ FAQ - Perguntas Frequentes

### Meu servidor raijin não está configurado ainda

**Resposta**: Você precisa primeiro configurar a infraestrutura:
```bash
# Instalar módulos necessários
raijin install kubernetes
raijin install argocd
raijin install harbor
raijin install vault
raijin install traefik
```
Depois volte aqui para publicar seus apps.

### Qual documento devo usar?

**Resposta**: Depende da sua experiência:
- **Primeiro app**: [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) + [COPILOT_PROMPT.md](COPILOT_PROMPT.md)
- **Já publiquei antes**: [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)
- **DevOps/Scripts**: [AGENT_GUIDE.md](AGENT_GUIDE.md)

### Posso publicar qualquer tipo de app?

**Sim!** Funciona com:
- ✅ Websites estáticos (HTML/CSS/JS)
- ✅ SPAs (React, Vue, Angular)
- ✅ APIs REST (Go, Python, Node, Java)
- ✅ Full-stack (Next.js, Nuxt, SvelteKit)
- ✅ Aplicações legacy (containerizadas)

### Preciso saber Kubernetes?

**Não necessariamente**:
- Use [COPILOT_PROMPT.md](COPILOT_PROMPT.md) - o Copilot gera tudo
- Siga [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) - passo a passo

Conhecimento básico ajuda, mas não é obrigatório.

### Quanto tempo leva?

**Primeira vez**: 3-5h (aprendendo)
**Apps seguintes**: 1-2h (processo conhecido)
**Com automação**: 30min (script pronto)

### Meu app ficará acessível na internet?

**Sim!** Com domínio próprio e HTTPS:
- TST: `myapp-tst.local` (interno)
- PRD: `myapp.com` (público na internet)

### Como funciona o deploy automático?

```
1. Você faz push no GitHub (branch develop ou main)
2. GitHub Actions builda Docker image
3. Push image para Harbor registry
4. ArgoCD detecta mudança
5. ArgoCD faz deploy no Kubernetes
6. App fica disponível em segundos
```

### Posso testar localmente antes?

**Sim!** Com Docker Compose:
```bash
docker-compose up
# Testa em http://localhost:3000
```

---

## 🎓 Habilidades Necessárias

### Mínimo (para COPILOT_PROMPT + EXAMPLE)
- ✅ Git básico (clone, commit, push)
- ✅ Docker básico (conceito de containers)
- ✅ Conhecimento do seu app (frontend/backend)
- ⚠️ Linha de comando básica

### Recomendado (para AGENT_GUIDE)
- ✅ Shell scripting
- ✅ Docker (build, multi-stage)
- ✅ Kubernetes básico (pods, deployments)
- ✅ CI/CD conceitos

### Avançado (para QUICK_START)
- ✅ Kubernetes (Kustomize, manifests)
- ✅ CI/CD pipelines
- ✅ GitOps (ArgoCD)
- ✅ DevOps best practices

---

## 📦 O Que Você Vai Ter ao Final

Seu app publicado e rodando:

```
✅ Código no GitHub
✅ Pipeline CI/CD configurado
✅ Build automático ao push
✅ Deploy automático em TST
✅ Deploy manual em PRD (aprovação)
✅ App acessível na internet: https://seuapp.com
✅ SSL/HTTPS automático
✅ Secrets seguros (Vault)
✅ Monitoring ativo (Prometheus/Grafana)
✅ Logs centralizados (Loki)
```

**Workflow completo**:
```
Developer push código
         ↓
GitHub Actions CI
  - Build Docker
  - Scan segurança
  - Push Harbor
         ↓
ArgoCD detecta mudança
  - Deploy TST (auto)
  - Deploy PRD (manual)
         ↓
App rodando na internet! 🚀
```

---

## 🔗 Links Rápidos

| Documento | Tamanho | Ideal para | Tempo |
|-----------|---------|------------|-------|
| [README.md](README.md) | 11KB | Navegação | 10min |
| [COPILOT_PROMPT.md](COPILOT_PROMPT.md) | 17KB | Iniciantes + Copilot | 3-5h |
| [AGENT_GUIDE.md](AGENT_GUIDE.md) | 28KB | DevOps + Automação | 2-4h |
| [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md) | 10KB | Experientes + MVP | 1-2h |
| [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) | 14KB | Todos + Aprendizado | 4-6h |

---

## 🎯 Próximos Passos

### 1️⃣ Se é sua primeira vez aqui
```bash
# Leia este arquivo até o final ← Você está aqui
# Depois escolha um dos fluxos acima
```

### 2️⃣ Depois de escolher o guia
```bash
# Abra o documento escolhido
# Siga as instruções
# Valide cada etapa
```

### 3️⃣ Quando terminar
```bash
# Deploy seu projeto
# Configure monitoring
# Documente customizações
```

---

## 📚 Recursos Adicionais

- **Raijin Docs**: `../` (pasta pai)
- **Exemplos**: `../../examples/monorepo-app/`
- **Pipelines**: `../../examples/ci-cd/`
- **Secrets**: `../../examples/secrets/`

---

## 🆘 Precisa de Ajuda?

1. Verifique FAQ acima
2. Consulte seção de troubleshooting em cada guia
3. Veja [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) para problemas comuns
4. Abra issue no repositório

---

**Boa configuração! 🚀**

---

_Última atualização: 2026-02-05_
