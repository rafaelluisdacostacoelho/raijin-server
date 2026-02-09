# Configuração SSH para GitHub

Este guia mostra como configurar acesso SSH ao GitHub a partir do servidor Kubernetes.

## Servidor: thor@asgard (192.168.1.81)

### 1. Chave SSH já gerada

Chave pública do servidor:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIP6zsi/Hzj2Z71GYCPXWFlKqHVJQQAQnlB5L8KMvd4f+ thor@asgard
```

### 2. Adicionar Chave no GitHub

1. Acesse: https://github.com/settings/ssh/new
2. Cole a chave pública acima
3. Título sugerido: `thor@asgard - Kubernetes Server`
4. Salve com **Add SSH key**

### 3. Adicionar aos Deploy Keys (para repo específico)

**Para repositório privado:**

1. Vá para: `https://github.com/skelvynks/supabase/settings/keys`
2. Clique em **Add deploy key**
3. Título: `thor@asgard - Kubernetes Deployment`
4. Cole a mesma chave pública
5. ✅ **Marque "Allow write access"** (necessário para push de CI/CD)
6. Clique em **Add key**

### 4. Testar Conexão

No servidor:
```bash
ssh thor@192.168.1.81
ssh -T git@github.com
# Deve retornar: Hi skelvynks! You've successfully authenticated...
```

### 5. Clonar Repositório

```bash
git clone git@github.com:skelvynks/supabase.git
```

## Acesso ao Servidor

### Via VS Code/Local

```bash
ssh -i ~/.ssh/id_ed25519 thor@192.168.1.81
```

### Executar Comandos Direto

```bash
ssh -i ~/.ssh/id_ed25519 thor@192.168.1.81 'comando aqui'
```

## Usage no Módulo GitOps

Após configurar SSH, usar URL SSH no gitops:

```bash
source ~/.venvs/midgard/bin/activate
raijin-server --skip-validation gitops
# URL: git@github.com:skelvynks/supabase.git
# (restante das entradas igual)
```

## Troubleshooting

### "Permission denied (publickey)"
- Verifique se a chave foi adicionada no GitHub
- Para repos privados, use Deploy Keys com write access

### "Host key verification failed"
```bash
ssh -i ~/.ssh/id_ed25519 thor@192.168.1.81 'ssh-keyscan github.com >> ~/.ssh/known_hosts'
```

### Ver chave pública novamente
```bash
ssh -i ~/.ssh/id_ed25519 thor@192.168.1.81 'cat ~/.ssh/id_ed25519.pub'
```

## Referências

- [GitHub SSH Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
- [Deploy Keys](https://docs.github.com/en/developers/overview/managing-deploy-keys)
