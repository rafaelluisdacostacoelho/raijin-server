# Versionamento e Tags

Este documento descreve o esquema de versionamento usado no Raijin Server.

## Semantic Versioning (SemVer)

Usamos [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

| Componente | Quando incrementar |
|------------|-------------------|
| **MAJOR** | Mudanças incompatíveis com versões anteriores |
| **MINOR** | Novas funcionalidades compatíveis |
| **PATCH** | Correções de bugs compatíveis |

## Esquema de Tags

Todas as tags seguem o padrão `vX.Y.Z`:

```bash
# Listar tags
git tag -l | sort -V

# Ver detalhes de uma tag
git show v0.3.0
```

## Histórico de Versões

### v0.3.0 (Atual)
**VPN-First Security Release**
- ✅ Módulo `vpn-client` para gerenciar clientes WireGuard
- ✅ Módulo `internal-dns` para domínios internos (*.asgard.internal)
- ✅ Documentação de acesso seguro via VPN
- ✅ Scripts de port-forward automatizados
- ✅ README.md completamente reescrito

### v0.2.41
- Documentação de operações MinIO
- Guia de monitoramento e alertas

### v0.2.36
- MinIO com recursos configuráveis
- Suporte a replicas em standalone mode

### v0.2.34
- SSH hardening aprimorado
- Detecção automática de usuário
- Melhor handling de chaves SSH

### v0.2.31
- Safety checks em uninstall de módulos
- Handling de CRDs em desinstalação

### v0.2.25
- Atualização do comando Istio
- Melhorias de estabilidade

### v0.2.10
- Suporte a MetalLB para LoadBalancer em bare metal
- Documentação atualizada

### v0.2.7
- Hardening de instalações
- Melhorias em diagnósticos

### v0.2.0
- Primeira versão com todos os módulos core
- Menu interativo
- Modo dry-run

### v0.1.0
- Release inicial
- Módulos básicos de bootstrap

## Convenções de Commit

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Tipos de Commit

| Tipo | Descrição |
|------|-----------|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Apenas documentação |
| `style` | Formatação (sem mudança de código) |
| `refactor` | Refatoração de código |
| `test` | Adição/correção de testes |
| `chore` | Manutenção (build, deps, etc.) |

### Exemplos

```bash
# Nova funcionalidade
git commit -m "feat(vpn): add client management module"

# Correção de bug
git commit -m "fix(kubernetes): handle missing kubeconfig"

# Documentação
git commit -m "docs: update README with venv instructions"

# Breaking change
git commit -m "feat(api)!: change CLI argument format"
```

## Criando uma Nova Release

### Método Automatizado (Recomendado)

O script `release.sh` automatiza todo o processo:

```bash
# Ativar venv de publicação
source ~/.venvs/publish/bin/activate

# Release simples
./release.sh 0.3.1

# Com mensagem personalizada
./release.sh 0.3.1 -m "feat: add new security module"

# Simular sem executar (dry-run)
./release.sh 0.3.1 --dry-run

# Apenas local (sem push)
./release.sh 0.3.1 --no-push

# Apenas git (sem PyPI)
./release.sh 0.3.1 --no-pypi
```

**O script executa automaticamente:**
1. ✅ Valida formato SemVer da versão
2. ✅ Verifica se tag já existe
3. ✅ Commita alterações pendentes (com confirmação)
4. ✅ Atualiza versão em `setup.cfg` e `__init__.py`
5. ✅ Cria commit de versão
6. ✅ Cria tag anotada
7. ✅ Faz push (commits + tags)
8. ✅ Build do pacote
9. ✅ Publica no PyPI
10. ✅ Cria GitHub Release (se `gh` CLI instalado)

### Opções do release.sh

| Opção | Descrição |
|-------|-----------|
| `-m, --message <msg>` | Mensagem personalizada da release |
| `-n, --no-push` | Não fazer push automático |
| `-p, --no-pypi` | Não publicar no PyPI |
| `-d, --dry-run` | Simular sem executar |
| `-h, --help` | Mostrar ajuda |

### Método Manual (se necessário)

```bash
# 1. Atualizar versão em setup.cfg e __init__.py
# 2. Commit
git commit -am "chore: bump version to X.Y.Z"
# 3. Tag
git tag -a vX.Y.Z -m "Release vX.Y.Z"
# 4. Push
git push origin master --tags
# 5. Build e publicar
python -m build && python -m twine upload dist/*
```

### GitHub CLI (Opcional)

Para criar GitHub Releases automaticamente:

```bash
# Instalar
sudo apt install gh

# Autenticar
gh auth login

# O release.sh usará automaticamente
```

## Verificando Tags no GitHub

Após o push, as tags aparecem em:
- **Releases:** `https://github.com/rafaelluisdacostacoelho/raijin-server/releases`
- **Tags:** `https://github.com/rafaelluisdacostacoelho/raijin-server/tags`

## Instalando Versão Específica

```bash
# Do PyPI
pip install raijin-server==0.3.0

# Do GitHub (via tag)
pip install git+https://github.com/rafaelluisdacostacoelho/raijin-server@v0.3.0
```
