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

### 1. Atualizar versão

```bash
# Editar setup.cfg
vim setup.cfg
# Alterar: version = X.Y.Z
```

### 2. Commit da versão

```bash
git add setup.cfg
git commit -m "chore: bump version to X.Y.Z"
```

### 3. Criar tag anotada

```bash
git tag -a vX.Y.Z -m "feat: descrição da release"
```

### 4. Push com tags

```bash
git push origin master --tags
```

### 5. Publicar no PyPI

```bash
source ~/.venvs/publish/bin/activate
rm -rf dist build
python -m build
./release.sh X.Y.Z
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
