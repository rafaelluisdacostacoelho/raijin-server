# Acesso SSH seguro a partir do Windows

Guia rápido para gerar uma chave pública no Windows e usá-la no módulo `ssh-hardening` do Raijin Server.

## Pré-requisitos
- Windows 10/11 com OpenSSH Client habilitado (já vem por padrão). Se não aparecer `ssh` no PowerShell, ative em *Configurações ➜ Aplicativos ➜ Recursos opcionais ➜ OpenSSH Client*.
- Acesso ao servidor Ubuntu onde o `ssh-hardening` será executado.

## Gerar (ou reutilizar) a chave pública no Windows
1) Verifique se já existe uma chave:
   - PowerShell: `dir ~/.ssh`
   - Se existir `id_ed25519.pub` (ou `id_rsa.pub`), mostre o conteúdo: `Get-Content ~/.ssh/id_ed25519.pub`
2) Se não houver chave, gere uma nova (recomendado ED25519):
   - PowerShell: `ssh-keygen -t ed25519 -C "seu_email"`
   - Aceite o caminho padrão (`C:\Users\SEUUSUARIO\.ssh\id_ed25519`) e defina uma passphrase (ou deixe vazio se aceitar o risco).
3) Copie a chave pública para uso no Raijin:
   - `Get-Content ~/.ssh/id_ed25519.pub`
   - A saída deve começar com `ssh-ed25519` em uma única linha.

## Executar o módulo `ssh-hardening`
No servidor Ubuntu (logado como root ou com sudo preservando o venv):

```bash
sudo -E ~/.venvs/midgard/bin/raijin-server ssh-hardening
```

Responda aos prompts:
- Usuário administrativo: ex.: `adminops` (será criado se não existir).
- Porta SSH: `22` ou outra; o módulo abre a porta escolhida no UFW e remove a 22 se trocar.
- Adicionar ao sudo: escolha `Y` se precisar de privilégios elevados.
- Caminho da chave pública: deixe vazio para `~/.ssh/id_ed25519.pub` ou cole manualmente quando solicitado.

O módulo aplica:
- Login somente por chave pública (PasswordAuthentication desativado).
- `PermitRootLogin no`, `MaxAuthTries 3`, `ClientAliveInterval 300`.
- Drop-in em `/etc/ssh/sshd_config.d/99-raijin.conf` e Fail2ban em `/etc/fail2ban/jail.d/raijin-sshd.conf`.

> Dica: mantenha a sessão atual aberta até testar o novo acesso.

## Testar o acesso após o hardening
- Conexão direta:

```bash
ssh adminops@IP_DO_SERVIDOR -p 22
```

- Opcional: adicionar ao `~/.ssh/config` (Windows). Crie o arquivo se não existir:

```
Host raijin
  HostName IP_DO_SERVIDOR
  User adminops
  Port 22
  IdentityFile ~/.ssh/id_ed25519
```

Depois conecte com `ssh raijin`.

## Problemas comuns
- "Permission denied": confira se colou a chave pública completa (uma linha) e se usou o usuário correto informado no módulo.
- Porta fechada: verifique o UFW (`sudo ufw status`) e, se houver firewall externo/roteador, abra a porta definida no módulo.
- Chave errada: se gerou outra chave, a pública fica em `C:\Users\SEUUSUARIO\.ssh\id_ed25519.pub`; a privada correspondente deve estar em `id_ed25519` no mesmo diretório.
