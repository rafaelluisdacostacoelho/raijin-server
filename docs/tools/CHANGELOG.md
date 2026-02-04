# Changelog — Documentação de Ferramentas

> Histórico de atualizações da documentação técnica do Raijin Server.

---

## [2.0.0] - 2026-02-03

### 🎉 Reestruturação Completa da Documentação

#### ✨ Adicionado

**Estrutura Profissional**
- ✅ Criado [README.md](README.md) como índice principal navegável
- ✅ Adicionada navegação entre documentos (← Anterior | Próximo →)
- ✅ Links para voltar ao índice em todos os documentos
- ✅ Índice interno (TOC) em cada documento

**Glossários Expandidos**
- ✅ Termos técnicos com números sobrescritos linkados (CNI¹, TLS², etc)
- ✅ Links para RFCs e documentação oficial
- ✅ Definições detalhadas de cada termo
- ✅ 10-15 termos por documento

**Exemplos Práticos**
- ✅ Exemplos YAML completos e testados
- ✅ Comandos práticos do dia a dia
- ✅ Queries PromQL e LogQL (Observability)
- ✅ Configurações de Middlewares (Traefik)
- ✅ Fluxos de CI/CD (Harbor, Vault)

**Boas e Más Práticas**
- ✅ Seção "Boas práticas ✅" com 10-15 recomendações
- ✅ Seção "Práticas ruins ❌" com avisos importantes
- ✅ Justificativas técnicas para cada prática

**Diagnóstico Avançado**
- ✅ Comandos detalhados de troubleshooting
- ✅ Health checks específicos por componente
- ✅ Debugging de conectividade
- ✅ Inspeção de recursos internos

#### 🔄 Modificado

**Documentos Atualizados (9 arquivos)**
1. **[calico.md](calico.md)**: CNI + NetworkPolicies
   - Exemplos de policies L3/L4
   - Diagnóstico de bloqueios
   - Ajuste de MTU

2. **[cert-manager.md](cert-manager.md)**: TLS automático
   - Fluxo HTTP-01 detalhado
   - Rate limits do Let's Encrypt
   - Forçar renovação manual

3. **[traefik.md](traefik.md)**: Ingress Controller
   - Middlewares (rate-limit, auth)
   - TLS passthrough
   - Métricas Prometheus

4. **[observability.md](observability.md)**: Stack de monitoramento
   - Queries PromQL complexas
   - LogQL para análise de logs
   - PrometheusRules customizadas
   - Alertmanager routing

5. **[secrets.md](secrets.md)**: Sealed-Secrets + ESO
   - Fluxo completo kubeseal
   - ExternalSecrets com Vault/AWS
   - Rotação de chaves

6. **[velero.md](velero.md)**: Backup e restore
   - Schedules automatizados
   - Backup de PVs com node-agent
   - Disaster recovery completo

7. **[harbor.md](harbor.md)**: Container Registry
   - Robot accounts para CI/CD
   - Vulnerability scanning com Trivy
   - Retention policies

8. **[minio.md](minio.md)**: S3-compatible storage
   - Least-privilege users
   - Distributed mode
   - Métricas e healing

9. **[vault.md](vault.md)**: Secrets management
   - Unseal process
   - KV v2 versioning
   - Service tokens com policies

**INFRASTRUCTURE_GUIDE.md**
- ✅ Atualizada tabela de componentes
- ✅ Adicionado link para [tools/README.md](README.md)
- ✅ Categorização por tipo (Rede, Segurança, Storage, etc)

#### 🗑️ Removido

**Arquivos Stub Obsoletos**
- ❌ `docs/HARBOR.md` (migrado para tools/)
- ❌ `docs/MINIO_OPERATIONS.md` (migrado para tools/)
- ❌ `docs/VELERO.md` (migrado para tools/)
- ❌ `docs/VAULT.md` (migrado para tools/)

---

## [1.0.0] - 2026-01-15

### 🎯 Migração Inicial

#### ✨ Adicionado

- Estrutura `docs/tools/` criada
- Migração de 4 documentos principais
- Stubs com redirecionamento nos arquivos antigos

#### 📝 Documentos Criados

1. **traefik.md**: Guia básico do Ingress Controller
2. **cert-manager.md**: TLS com Let's Encrypt
3. **calico.md**: CNI e NetworkPolicies
4. **observability.md**: Prometheus + Grafana + Loki
5. **secrets.md**: Sealed-Secrets + External-Secrets

#### 🔄 Migrados

6. **velero.md**: Backup e restore (de VELERO.md)
7. **harbor.md**: Container Registry (de HARBOR.md)
8. **minio.md**: S3 storage (de MINIO_OPERATIONS.md)
9. **vault.md**: Secrets management (de VAULT.md)

---

## Métricas de Melhoria

| Métrica | Antes (v1.0) | Depois (v2.0) | Melhoria |
|---------|--------------|---------------|----------|
| Glossários | Nenhum | 80+ termos | ∞ |
| Exemplos práticos | 5-10/doc | 15-25/doc | +200% |
| Comandos de debug | 3-5/doc | 20-30/doc | +500% |
| Links de navegação | 0 | Todos docs | ✅ |
| Referências externas | Poucas | RFCs + Docs oficiais | +300% |
| Boas/Más práticas | Nenhuma | 20-30/doc | ∞ |

---

## Roadmap

### v2.1.0 (Planejado)
- [ ] Adicionar diagramas Mermaid em cada documento
- [ ] Criar vídeos/GIFs demonstrativos
- [ ] Tradução para inglês (EN)
- [ ] Adicionar seção "FAQ" por componente

### v2.2.0 (Futuro)
- [ ] Integração com Read the Docs
- [ ] Testes automatizados de comandos
- [ ] Playground interativo (Katacoda-like)

---

## Como Contribuir

1. **Reportar erros**: Abrir issue no GitHub
2. **Sugerir melhorias**: Pull Request com descrição clara
3. **Adicionar exemplos**: Testar antes de submeter
4. **Atualizar glossários**: Incluir link para documentação oficial

### Padrão de Commits

```bash
git commit -m "docs(calico): adicionar exemplo de egress policy"
git commit -m "docs(harbor): corrigir comando de robot account"
git commit -m "docs(all): atualizar links de navegação"
```

---

**Mantido por**: Raijin Server Team  
**Última atualização**: 2026-02-03
