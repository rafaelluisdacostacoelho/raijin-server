# Cert-Manager (TLS Automático)

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Calico](calico.md) | [Próximo: Traefik →](traefik.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Manutenção](#manutenção-e-monitoramento)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- Operador que emite e renova certificados **TLS¹** para recursos Ingress/Certificate.
- Usamos issuers `letsencrypt-staging` e `letsencrypt-prod` pré-instalados.
- Integração com **ACME²** (Let's Encrypt) via desafio **HTTP-01³**.

## Por que usamos
- Automação completa do ciclo de vida de certificados (emissão, renovação, rotação).
- Suporte a HTTP-01 via Traefik sem dependências extras.
- Elimina certificados manuais e expirações silenciosas.

## Como está configurado no Raijin (V1)
- **Issuers**: `letsencrypt-staging` e `letsencrypt-prod` já instalados como **ClusterIssuers⁴**.
- **Desafio**: HTTP-01, respondido pelo Traefik.
- **Fluxo padrão**: adicionar annotation `cert-manager.io/cluster-issuer: "letsencrypt-prod"` no Ingress; o Cert-Manager cria `Certificate` e gerencia o Secret `<nome>-tls`.
- **Renovação**: automática ~30 dias antes da expiração (rate limit⁵ do Let's Encrypt: 50 certs/domínio/semana).
- **Solver**: Traefik responde ao desafio HTTP-01 criando rota temporária `/.well-known/acme-challenge/`.

## O que o Cert-Manager resolve na nossa arquitetura
- Emissão e renovação automática de certificados públicos (Let's Encrypt) para todos os Ingresses.
- Gestão padronizada de Secrets TLS, evitando certificados manuais e expiração silenciosa.
- Observabilidade do ciclo de vida via recursos Kubernetes (Certificate, Order, Challenge).

## Como operamos
- Listar certificados: `kubectl get certificate -A`.
- Ver issuers: `kubectl get clusterissuers`.
- Fluxo padrão: adicionar `cert-manager.io/cluster-issuer: "letsencrypt-prod"` no Ingress. O Cert-Manager cria o recurso Certificate e gerencia o Secret `<nome>-tls`.

## Manutenção e monitoramento
- Saúde: `kubectl get pods -n cert-manager` e logs do controller `kubectl logs -n cert-manager -l app.kubernetes.io/component=controller`.
- Validade: `kubectl get certificate -A` para expiração; `kubectl describe certificate <nome> -n <ns>` mostra status e eventos de renovação.
- Challenges: `kubectl get challenges -A` e `kubectl describe challenge <nome> -n <ns>` para debugar falhas HTTP-01.
- Registros DNS: garantir que hosts apontem para o endpoint do Traefik (A/CNAME); sem isso, o HTTP-01 falha.
- Atualizações: manter a versão alinhada com o chart principal; testar em staging.

## Troubleshooting
- Detalhes de um certificado: `kubectl describe certificate <nome> -n <ns>`.
- Ver challenges: `kubectl get challenges -A` e `kubectl describe challenge <nome> -n <ns>`.
- Logs do controlador: `kubectl logs -n cert-manager -l app.kubernetes.io/component=controller`.
- Check de DNS: `nslookup <host>` precisa apontar para o IP atendido pelo Traefik.

## Links úteis
- https://cert-manager.io/docs/

---

## Glossário

1. **TLS** (Transport Layer Security): Protocolo criptográfico para comunicação segura (sucessor do SSL).
2. **ACME** (Automated Certificate Management Environment): Protocolo de emissão/renovação automática de certificados (usado pelo Let's Encrypt).
3. **HTTP-01**: Desafio ACME que valida domínio via arquivo acessível em `http://<dominio>/.well-known/acme-challenge/<token>`.
4. **ClusterIssuer**: Recurso do Cert-Manager que emite certificados para qualquer namespace (escopo cluster).
5. **Rate Limit**: Limite de requisições do Let's Encrypt (50 certificados/domínio/semana; use staging para testes).
6. **DNS-01**: Desafio ACME alternativo que valida via registro TXT no DNS (suporta wildcards; não usado no Raijin V1).
7. **Certificate**: Recurso Kubernetes gerenciado pelo Cert-Manager representando um certificado TLS.
8. **Order**: Recurso intermediário criado durante emissão (representa pedido ao ACME).
9. **Challenge**: Recurso representando validação específica (HTTP-01 ou DNS-01).
10. **Secret**: Onde o certificado TLS final é armazenado (`tls.crt` + `tls.key`).

---

## Exemplos práticos

### Ingress básico com TLS automático

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  namespace: apps
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - myapp.example.com
    secretName: myapp-tls
  rules:
  - host: myapp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp
            port:
              number: 80
```

### Testar com staging primeiro

```yaml
annotations:
  cert-manager.io/cluster-issuer: "letsencrypt-staging"  # Testar antes
```

### Forçar renovação manual

```bash
kubectl delete secret myapp-tls -n apps
kubectl delete certificate myapp-tls -n apps
# Cert-Manager recria automaticamente
```

### Verificar validade do certificado

```bash
kubectl get certificate myapp-tls -n apps
kubectl describe certificate myapp-tls -n apps
openssl s_client -connect myapp.example.com:443 -servername myapp.example.com < /dev/null | openssl x509 -noout -dates
```

---

## Boas práticas ✅

1. **Staging primeiro**: Sempre testar com `letsencrypt-staging` antes de usar `letsencrypt-prod` (evita rate limits).
2. **DNS pronto**: Garantir que `A`/`CNAME` aponta para o IP do Traefik antes de aplicar Ingress.
3. **Secret único por host**: Não reutilizar o mesmo `secretName` para hosts diferentes.
4. **Monitorar expiração**: Configurar alertas para certificados próximos da expiração (30 dias).
5. **Namespace correto**: Secret TLS fica no mesmo namespace do Ingress.
6. **Wildcard via DNS-01**: Se precisar de `*.example.com`, usar ClusterIssuer com DNS-01 (requer integração com provider DNS).
7. **Backup de Secrets**: Incluir Secrets `*-tls` em backups do Velero.
8. **Revisar events**: Monitorar eventos de Certificate para detectar falhas cedo.
9. **HTTP antes de HTTPS**: Validar app funcionando em HTTP antes de adicionar TLS.
10. **Documentar domínios**: Manter lista de domínios gerenciados pelo Cert-Manager.

---

## Práticas ruins ❌

1. **Produção sem staging**: Usar `letsencrypt-prod` direto pode esgotar rate limits em caso de erro.
2. **DNS incorreto**: Aplicar Ingress sem DNS configurado causa falha no HTTP-01.
3. **Secret duplicado**: Reutilizar `secretName` entre Ingresses diferentes causa conflito.
4. **Não monitorar**: Ignorar events/logs pode deixar certificados expirarem silenciosamente.
5. **Deletar ClusterIssuer**: Remover issuer quebra renovação de todos os certificados.
6. **HTTP-01 sem Ingress**: Tentar emitir Certificate standalone sem Ingress (HTTP-01 precisa de rota pública).
7. **Rate limit esgotado**: Fazer muitas tentativas em produção sem debugar em staging.
8. **Portas bloqueadas**: Firewalls bloqueando porta 80 impedem validação HTTP-01.
9. **Cert-Manager desatualizado**: Usar versão antiga com bugs conhecidos de renovação.
10. **Múltiplos issuers no mesmo Ingress**: Conflito de annotations pode causar loop de renovação.

---

## Diagnóstico avançado

### Ver status completo do certificado

```bash
kubectl describe certificate myapp-tls -n apps
kubectl get certificate myapp-tls -n apps -o yaml
```

### Inspecionar Order e Challenge

```bash
kubectl get orders -n apps
kubectl describe order <order-name> -n apps
kubectl get challenges -n apps
kubectl describe challenge <challenge-name> -n apps
```

### Logs do controller

```bash
kubectl logs -n cert-manager -l app.kubernetes.io/component=controller --tail=100 -f
```

### Validar DNS antes de aplicar

```bash
nslookup myapp.example.com
dig myapp.example.com +short
```

### Testar HTTP-01 manualmente

```bash
curl -v http://myapp.example.com/.well-known/acme-challenge/test
```

### Ver Secret TLS

```bash
kubectl get secret myapp-tls -n apps
kubectl get secret myapp-tls -n apps -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -text
```

### Forçar re-issue imediato

```bash
kubectl annotate certificate myapp-tls -n apps cert-manager.io/issue-temporary-certificate="true" --overwrite
```

### Verificar rate limits do Let's Encrypt

- Rate limits: https://letsencrypt.org/docs/rate-limits/
- Status: https://letsencrypt.status.io/

### Checar conectividade Cert-Manager → Let's Encrypt

```bash
kubectl exec -n cert-manager -it deployment/cert-manager -- curl -v https://acme-v02.api.letsencrypt.org/directory
```
