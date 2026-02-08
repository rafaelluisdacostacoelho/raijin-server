# Publicar Novos Apps - Guias e Templates

Esta pasta contém documentação e templates para **publicar novos aplicativos** (websites, APIs, SPAs) na infraestrutura raijin-server já configurada.

## 🎯 Objetivo

Você tem um servidor Kubernetes produtivo configurado pelo raijin-server. Agora você quer:
- Desenvolver novos apps (e-commerce, blog, API, dashboard, etc.)
- Publicar automaticamente via CI/CD (GitHub → Build → Deploy)
- Expor na internet via Traefik ingress
- Gerenciar secrets com Vault
- Monitorar com Prometheus/Grafana

---

## 📚 Documentos Disponíveis

### 1. [COPILOT_PROMPT.md](COPILOT_PROMPT.md)
**Para**: Copilot Chat, Claude, ChatGPT, ou qualquer LLM
**Quando usar**: Você tem um novo app e quer publicá-lo automaticamente via CI/CD
**Conteúdo**:
- Contexto completo da stack raijin-server
- Instruções detalhadas passo a passo
- Exemplos de código completos
- Checklist de validação
- Referências e documentação

**Como usar**:
```
1. Abra o Copilot Chat no VS Code (Ctrl+Shift+I)
2. Cole o conteúdo ou referência: "@COPILOT_PROMPT.md"
3. Adicione detalhes do seu projeto:
   - Tecnologias (React, Go, etc.)
   - Requisitos específicos
   - Nome do projeto
4. O Copilot irá criar toda a estrutura
```

**Exemplo de prompt**:
```
Usando como base @COPILOT_PROMPT.md, publique meu app:
- Frontend: Next.js 14
- Backend: Go com Fiber
- Database: PostgreSQL + Redis
- Nome: ecommerce-platform
- Domínio: shop.example.com
- Infraestrutura raijin-server já configurada
```

---

### 2. [AGENT_GUIDE.md](AGENT_GUIDE.md)
**Para**: Agentes autônomos, scripts de automação, CI/CD
**Quando usar**: Você quer automatizar a configuração ou entender o processo técnico detalhado
**Conteúdo**:
- Comandos shell executáveis
- Validações automatizadas
- Scripts de setup completos
- Troubleshooting técnico
- Checklist automatizado

**Como usar**:
```bash
# 1. Seguir manualmente passo a passo
cat AGENT_GUIDE.md

# 2. Extrair comandos e executar
grep -A 10 "```bash" AGENT_GUIDE.md

# 3. Usar com um agente autônomo
agent --task "Configure monorepo seguindo AGENT_GUIDE.md"
```

**Ideal para**:
- DevOps criando scripts de automação
- CI/CD pipelines que fazem bootstrap de projetos
- Desenvolvedores que preferem linha de comando
- Entender tecnicamente cada etapa

---

### 3. [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)
**Para**: Desenvolvedores experientes, setup rápido
**Quando usar**: Você já conhece a stack e quer apenas os comandos/templates essenciais
**Conteúdo**:
- Prompt condensado
- Variáveis de configuração
- Comandos one-liner
- Templates mínimos
- Troubleshooting rápido

**Como usar**:
```bash
# 1. Configurar variáveis
export PROJECT_NAME="myapp"
export HARBOR_REGISTRY="192.168.1.100:30880"

# 2. Copiar templates necessários
# 3. Substituir variáveis
# 4. Deploy
```

**Ideal para**:
- Criar MVPs rapidamente
- Protótipos e demos
- Quando você já fez isso antes
- Referência rápida

---

### 4. [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) ⭐
**Para**: Todos os níveis
**Quando usar**: Você quer ver um exemplo completo do início ao fim
**Conteúdo**:
- Exemplo real: E-commerce Platform
- Passo a passo completo desde prompt até deploy
- Validações em cada etapa
- Comandos executados com outputs esperados
- Troubleshooting de problemas reais

**Como usar**:
```bash
# Seguir o exemplo linha por linha
# Adaptar para seu projeto
# Usar como referência de validação
```

**Ideal para**:
- Primeira vez configurando monorepo
- Entender o workflow completo
- Validar se fez tudo corretamente
- Aprender com exemplo prático

---

## 🎯 Qual Documento Usar?

| Situação | Documento | Motivo |
|----------|-----------|--------|
| Primeiro app que vou publicar | COPILOT_PROMPT.md + EXAMPLE_ECOMMERCE.md | Assistência IA + exemplo prático |
| Criar script de publicação | AGENT_GUIDE.md | Comandos prontos e validações |
| Publicar app simples rápido | QUICK_START_TEMPLATE.md | Templates mínimos |
| Entender processo de publicação | AGENT_GUIDE.md | Passo a passo técnico |
| Ensinar equipe a publicar apps | COPILOT_PROMPT.md + EXAMPLE_ECOMMERCE.md | Contexto + exemplo real |
| Automatizar publicação | AGENT_GUIDE.md | Automatizável e testável |
| Ver exemplo completo real | EXAMPLE_ECOMMERCE.md | Workflow do início ao fim |

---

## 🚀 Fluxo Recomendado

### Para Iniciantes

1. **Leia** [COPILOT_PROMPT.md](COPILOT_PROMPT.md) para entender como publicar apps
2. **Use Copilot/Claude** com o prompt para gerar configuração do seu app
3. **Siga** [EXAMPLE_ECOMMERCE.md](EXAMPLE_ECOMMERCE.md) como referência
4. **Consulte** [AGENT_GUIDE.md](AGENT_GUIDE.md) para troubleshooting
5. **Publique** seu app em produção

### Para Experientes

1. **Consulte** [QUICK_START_TEMPLATE.md](QUICK_START_TEMPLATE.md)
2. **Copie** templates necessários (Dockerfile, Kubernetes, Pipeline)
3. **Customize** para seu app
4. **Deploy** em produção (1-2h)

### Para DevOps/Automação

1. **Baseie-se** em [AGENT_GUIDE.md](AGENT_GUIDE.md)
2. **Extraia** comandos shell
3. **Crie** scripts de publicação reutilizáveis
4. **Automatize** publicação de múltiplos apps

---

## 📁 Estrutura de Arquivos Gerados

Independente do documento usado, o resultado final será:

```
seu-projeto/
├── .github/
│   └── workflows/
│       ├── ci-tst.yml              # Pipeline TST (auto)
│       └── ci-prd.yml              # Pipeline PRD (manual)
├── frontend/
│   ├── Dockerfile                  # Build produção
│   ├── Dockerfile.dev              # Build dev com hot-reload
│   ├── nginx.conf                  # Config Nginx
│   └── src/                        # Código fonte
├── backend/
│   ├── Dockerfile                  # Build produção
│   ├── Dockerfile.dev              # Build dev
│   └── {cmd/,src/}                 # Código fonte
├── kubernetes/
│   ├── base/                       # Manifests base
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── frontend/
│   │   │   ├── deployment.yaml
│   │   │   └── service.yaml
│   │   ├── backend/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── configmap.yaml
│   │   ├── database/
│   │   │   ├── statefulset.yaml
│   │   │   ├── service.yaml
│   │   │   └── pvc.yaml
│   │   ├── externalsecrets.yaml    # Vault integration
│   │   └── ingress.yaml            # Traefik ingress
│   ├── overlays/
│   │   ├── tst/
│   │   │   ├── kustomization.yaml
│   │   │   └── patches/
│   │   └── prd/
│   │       ├── kustomization.yaml
│   │       └── patches/
│   ├── argocd-app-tst.yaml         # ArgoCD Application TST
│   └── argocd-app-prd.yaml         # ArgoCD Application PRD
├── scripts/
│   ├── vault-setup.sh              # Configurar secrets no Vault
│   └── dev.sh                      # Start dev environment
├── docker-compose.yml              # Dev local completo
├── Makefile                        # Comandos úteis
└── README.md                       # Documentação do projeto
```

---

## 🔧 Pré-requisitos

Antes de usar qualquer dos documentos, certifique-se que a infraestrutura raijin-server está instalada:

```bash
# 1. Verificar Kubernetes
kubectl cluster-info

# 2. Verificar módulos instalados
raijin list

# 3. Verificar componentes críticos
kubectl get pods -n argocd      # ArgoCD
kubectl get pods -n harbor      # Harbor Registry
kubectl get pods -n vault       # HashiCorp Vault
kubectl get pods -n traefik     # Traefik Ingress

# 4. Obter IPs/URLs importantes
kubectl get svc -A | grep -E "argocd|harbor|vault"
```

**Se algo estiver faltando**:
```bash
raijin install argocd
raijin install harbor
raijin install vault
raijin install traefik
```

---

## 🎓 Conceitos Importantes

### GitOps (Argo CD)
- **TST**: Auto-sync habilitado, deploy automático ao push em `develop`
- **PRD**: Sync manual, aprovação necessária para deploy

### Pipeline CI/CD
- **GitHub Actions**: Pipeline externo (GitHub runners)
- **Argo Workflows**: Pipeline interno (dentro do cluster)

### Secrets Management
- **Vault**: Armazenamento centralizado de secrets
- **External Secrets Operator**: Sincronização automática Vault → Kubernetes

### Registry
- **Harbor**: Private registry com scanning de vulnerabilidades
- **Trivy**: Scan de CVEs nas imagens Docker

---

## 📖 Exemplos de Uso

### Exemplo 1: E-commerce Monorepo

```bash
# 1. Usar Copilot
# Prompt: "Configure monorepo e-commerce com Next.js + Go + PostgreSQL"

# 2. Configurar variáveis (do template)
export PROJECT_NAME="ecommerce"
export DOMAIN_PRD="shop.example.com"

# 3. Setup secrets
./scripts/vault-setup.sh ecommerce

# 4. Deploy TST
git push origin develop

# 5. Verificar
kubectl get pods -n ecommerce-tst
```

### Exemplo 2: SaaS Platform

```bash
# 1. Seguir AGENT_GUIDE.md passo a passo
# 2. Customizar para microservices:
#    - frontend/ (Next.js)
#    - backend/api/ (Go)
#    - backend/worker/ (Python)
#    - backend/websocket/ (Node.js)

# 3. Ajustar Kustomize para múltiplos backends
# 4. Deploy
```

---

## 🆘 Suporte

### Problemas Comuns

**1. Harbor registry não acessível**
```bash
# Verificar LoadBalancer
kubectl get svc -n harbor harbor-portal

# Port-forward temporário
kubectl port-forward -n harbor svc/harbor-portal 30880:80
```

**2. Argo CD não sincroniza**
```bash
# Ver logs
kubectl logs -n argocd deployment/argocd-application-controller

# Forçar refresh
argocd app get <app-name> --refresh
```

**3. External Secret não cria secret**
```bash
# Verificar ESO
kubectl get externalsecret -A
kubectl describe externalsecret <name> -n <namespace>

# Verificar Vault
kubectl exec -n vault vault-0 -- vault kv get secret/myapp/database
```

### Mais Ajuda

- **Documentação Raijin**: `docs/`
- **Exemplos completos**: `examples/monorepo-app/`
- **Troubleshooting**: Cada documento tem seção específica
- **Issues**: Abra issue no repositório raijin-server

---

## 🔄 Atualizações

Estes documentos são atualizados quando:
- Novas features são adicionadas ao raijin-server
- Melhores práticas são descobertas
- Feedback da comunidade

**Última atualização**: 2026-02-05

---

## 🤝 Contribuindo

Encontrou um problema ou tem sugestão de melhoria?

1. Abra uma issue descrevendo o problema/sugestão
2. Ou faça um PR com a correção
3. Siga o style guide existente

---

## 📄 Licença

Estes documentos seguem a mesma licença do raijin-server.

---

## 🎯 Próximos Passos

Depois de configurar seu monorepo:

1. **Monitoring**:
   - Configure ServiceMonitor para Prometheus
   - Crie dashboards no Grafana
   - Configure alertas

2. **Security**:
   - Habilite Network Policies (Calico)
   - Configure Pod Security Standards
   - Habilite RBAC detalhado

3. **Backup**:
   - Configure Velero para backups
   - Schedule backups automáticos
   - Teste restore

4. **Scaling**:
   - Configure HPA (Horizontal Pod Autoscaler)
   - Configure VPA (Vertical Pod Autoscaler)
   - Teste load com K6

5. **Observability**:
   - Integre Loki para logs
   - Configure distributed tracing (Jaeger/Tempo)
   - Configure APM

---

**Boa sorte com seu projeto! 🚀**
