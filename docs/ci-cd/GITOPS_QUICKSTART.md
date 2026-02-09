# Quick Start: GitOps Automation

Automatize a configuração de CI/CD para seu repositório em **3 comandos**.

## Exemplo: Repositório Supabase Custom

```bash
# 1. Executar automation
raijin-server gitops
```

### Inputs

```
URL do repositório GitHub: https://github.com/skelvynks/supabase
Nome da aplicação [supabase]: supabase
Namespace Kubernetes [supabase]: supabase
Domínio: supabase.cryptidnest.com
Harbor Registry URL [harbor.cryptidnest.com]: 
Harbor Project [library]: 
Número de replicas [2]: 2

Configurar backup com Velero? [Y/n]: Y
Commitar e fazer push das mudanças? [Y/n]: Y
Aplicar ArgoCD Application agora? [Y/n]: Y
```

### O que acontece automaticamente

```
✓ Clone do repositório
✓ Detecção do tipo: supabase-custom
✓ Geração de Dockerfile
✓ Criação de k8s/
  ├─ namespace.yaml
  ├─ deployment.yaml
  ├─ service.yaml
  ├─ ingress.yaml
  ├─ hpa.yaml
  └─ argocd-application.yaml
✓ Criação de .github/workflows/cicd.yml
✓ Commit + Push
✓ Deploy ArgoCD Application
```

## 2. Configurar Secrets no GitHub

```bash
# No repositório GitHub:
# Settings → Secrets and variables → Actions → New repository secret

HARBOR_USERNAME: admin
HARBOR_PASSWORD: <sua-senha>
```

## 3. Push para Trigger Pipeline

```bash
git push origin main
```

## Pipeline Ativa! 🚀

```
Developer Push
    ↓
GitHub Actions
    ↓
Build Docker Image
    ↓
Push to Harbor (harbor.cryptidnest.com/library/supabase:sha-abc123)
    ↓
ArgoCD Detect Change
    ↓
Auto-Sync to Kubernetes
    ↓
Rolling Update Deployment
    ↓
Application Live!
    ↓
https://supabase.cryptidnest.com ✅
```

## Monitorar Deploy

```bash
# Status ArgoCD
kubectl get application supabase -n argocd -w

# Status pods
kubectl get pods -n supabase -w

# Logs
kubectl logs -n supabase -l app=supabase -f

# Testar endpoint
curl https://supabase.cryptidnest.com/health
```

## DNS no Cloudflare

Não esqueça de configurar o DNS:

```
Type: A
Name: supabase
IPv4: <IP-DO-SEU-SERVIDOR>
Proxy: OFF (cinza)
```

## Resultado Final

**✅ Pipeline CI/CD 100% funcional**:
- Git push → Auto-deploy
- Docker build automático
- Harbor registry integrado
- ArgoCD GitOps
- HTTPS com cert-manager
- Escalabilidade (HPA)
- Backup (Velero)

**🌐 Aplicação disponível**:
- https://supabase.cryptidnest.com

**📊 Monitoramento**:
- ArgoCD UI: https://argocd.cryptidnest.com
- Grafana: https://grafana.cryptidnest.com
- Harbor: https://harbor.cryptidnest.com

---

**Tempo total**: ~5 minutos

**Comandos executados**: 1 (raijin-server gitops)

**Arquivos gerados**: 10+

**Pronto para produção**: ✅

---

Documentação completa: [GITOPS_AUTOMATION.md](GITOPS_AUTOMATION.md)
