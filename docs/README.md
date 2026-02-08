# Raijin Server - Documentação

Documentação completa do Raijin Server, incluindo guias de infraestrutura, ferramentas e configuração de projetos.

---

## 📚 Índice

### 🏗️ Infraestrutura

- **[INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md)** - Guia completo da infraestrutura
- **[STACK.md](STACK.md)** - Stack tecnológica completa
- **[INTERNAL_DNS.md](INTERNAL_DNS.md)** - Configuração de DNS interno
- **[VPN_REMOTE_ACCESS.md](VPN_REMOTE_ACCESS.md)** - Acesso remoto via VPN
- **[PUBLIC_APPS.md](PUBLIC_APPS.md)** - Aplicações públicas

### 🔧 Ferramentas

Documentação detalhada de cada ferramenta instalada:

- [tools/kubernetes.md](tools/kubernetes.md) - Kubernetes (K3s)
- [tools/argocd.md](tools/argo.md) - Argo CD + Argo Workflows (GitOps)
- [tools/harbor.md](tools/harbor.md) - Harbor (Registry)
- [tools/vault.md](tools/vault.md) - HashiCorp Vault (Secrets)
- [tools/traefik.md](tools/traefik.md) - Traefik (Ingress)
- [tools/cert-manager.md](tools/cert-manager.md) - Cert Manager (SSL/TLS)
- [tools/prometheus.md](tools/prometheus.md) - Prometheus (Monitoring)
- [tools/grafana.md](tools/grafana.md) - Grafana (Dashboards)
- [tools/loki.md](tools/loki.md) - Loki (Logs)
- [tools/calico.md](tools/calico.md) - Calico (Network Policies)
- [tools/metallb.md](tools/metallb.md) - MetalLB (LoadBalancer)
- [tools/minio.md](tools/minio.md) - MinIO (Object Storage)
- [tools/velero.md](tools/velero.md) - Velero (Backup/Restore)

Ver lista completa: [tools/README.md](tools/README.md)

### 🚀 CI/CD e Publicação de Apps

**Publique novos aplicativos** na infraestrutura raijin-server com CI/CD automático:

- **[ci-cd/INDEX.md](ci-cd/INDEX.md)** - Ponto de entrada: escolha seu guia
- **[ci-cd/COPILOT_PROMPT.md](ci-cd/COPILOT_PROMPT.md)** - Prompt para Copilot/LLM publicar seu app
- **[ci-cd/AGENT_GUIDE.md](ci-cd/AGENT_GUIDE.md)** - Guia técnico com scripts de publicação
- **[ci-cd/QUICK_START_TEMPLATE.md](ci-cd/QUICK_START_TEMPLATE.md)** - Templates rápidos
- **[ci-cd/EXAMPLE_ECOMMERCE.md](ci-cd/EXAMPLE_ECOMMERCE.md)** - Exemplo prático completo

**Use quando precisar**:
- Publicar novo website/API/SPA no Kubernetes
- Configurar CI/CD para build automático
- Deploy automático via ArgoCD
- Expor app na internet com domínio próprio
- Gerenciar secrets com Vault

### 📋 Planejamento

- **[BACKLOG_V2.md](BACKLOG_V2.md)** - Roadmap e features futuras
- **[VERSIONING.md](VERSIONING.md)** - Estratégia de versionamento

### 🧪 Testes e Validação

- **[VPN_TEST.md](VPN_TEST.md)** - Testes de VPN
- **[SSH_WINDOWS.md](SSH_WINDOWS.md)** - SSH no Windows

### 🎨 Ferramentas Visuais

- **[VISUAL_TOOLS.md](VISUAL_TOOLS.md)** - Ferramentas de visualização e dashboards

---

## 🎯 Guias Rápidos

### Primeiro Uso

1. Leia [INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md)
2. Escolha e instale módulos com `raijin install <module>`
3. Configure DNS interno: [INTERNAL_DNS.md](INTERNAL_DNS.md)
4. Configure acesso remoto: [VPN_REMOTE_ACCESS.md](VPN_REMOTE_ACCESS.md)

### Publicar Novo Projeto/App

1. Leia [ci-cd/INDEX.md](ci-cd/INDEX.md) para escolher o guia adequado
2. Opções:
   - **Novo app**: Use [ci-cd/COPILOT_PROMPT.md](ci-cd/COPILOT_PROMPT.md) com Copilot
   - **Experiente**: Use [ci-cd/QUICK_START_TEMPLATE.md](ci-cd/QUICK_START_TEMPLATE.md)
   - **Automação**: Use [ci-cd/AGENT_GUIDE.md](ci-cd/AGENT_GUIDE.md)
3. Siga o [ci-cd/EXAMPLE_ECOMMERCE.md](ci-cd/EXAMPLE_ECOMMERCE.md) como referência
4. Publique: GitHub → CI/CD build → Deploy → Produção 🚀

### Troubleshooting

1. Verifique logs: `kubectl logs -n <namespace> <pod>`
2. Verifique status: `kubectl get all -n <namespace>`
3. Consulte documentação específica da ferramenta em `tools/`
4. Verifique [INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md) seção de troubleshooting

---

## 📂 Estrutura da Documentação

```
docs/
├── README.md (este arquivo)
├── INFRASTRUCTURE_GUIDE.md
├── STACK.md
├── INTERNAL_DNS.md
├── VPN_REMOTE_ACCESS.md
├── PUBLIC_APPS.md
├── BACKLOG_V2.md
├── VERSIONING.md
├── VPN_TEST.md
├── SSH_WINDOWS.md
├── VISUAL_TOOLS.md
├── ci-cd/                          # ← NOVO!
│   ├── README.md
│   ├── COPILOT_PROMPT.md
│   ├── AGENT_GUIDE.md
│   └── QUICK_START_TEMPLATE.md
└── tools/
    ├── README.md
    ├── kubernetes.md
    ├── argo.md
    ├── harbor.md
    ├── vault.md
    └── ... (outras ferramentas)
```

---

## 🔗 Links Úteis

### Repositórios Relacionados

- **Raijin Server**: https://github.com/your-org/raijin-server
- **Exemplos**: `../examples/`

### Documentação Externa

- **Kubernetes**: https://kubernetes.io/docs/
- **Argo CD**: https://argo-cd.readthedocs.io/
- **Harbor**: https://goharbor.io/docs/
- **Vault**: https://www.vaultproject.io/docs
- **Traefik**: https://doc.traefik.io/traefik/

### Comunidade

- Issues: GitHub Issues
- Discussions: GitHub Discussions

---

## 🤝 Contribuindo

Encontrou um erro ou quer melhorar a documentação?

1. Abra uma issue descrevendo o problema
2. Ou faça um Pull Request com a correção
3. Siga o estilo dos documentos existentes

---

## 📜 Licença

Esta documentação segue a mesma licença do Raijin Server.

---

**Última atualização**: 2026-02-05
