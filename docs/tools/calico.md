# Calico (CNI e Network Policy)

> **Navegação**: [← Voltar ao Índice](README.md) | [Próximo: Cert-Manager →](cert-manager.md)

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
- **[CNI](#1-cni)¹** (Container Network Interface) que provê rede pod-pod, roteamento e **[NetworkPolicies](#2-networkpolicy)²**.
- Mantemos modo padrão com políticas habilitadas e default-deny nos namespaces de apps.

## Por que usamos
- **[NetworkPolicies](#2-networkpolicy)²** granulares ([L3](#3-l3)³/[L4](#4-l4)⁴) para isolar workloads.
- Estável e amplamente usado em clusters bare metal.
- Controle de tráfego sem necessidade de [service mesh](#5-service-mesh)⁵.

## Como está configurado no Raijin (V1)
- Versão: Calico v3.27.2 (manifest oficial aplicado via `curl | kubectl apply`).
- Pod CIDR padrão: `10.244.0.0/16` (personalizável no prompt; substituído via `sed` no manifest antes do apply).
- Namespace de workloads: `apps` criado pelo módulo, com labels `raijin/workload-profile=production` e `networking.raijin.dev/default-egress=restricted`.
- Policies opinativas: `default-deny-all` aplicada nos namespaces escolhidos (por padrão, `apps`).
- Egress controlado: policy `allow-egress-internet` opcional para pods rotulados com `networking.raijin.dev/egress=internet`; CIDR padrão `0.0.0.0/0` (customizável).
- CNI em modo padrão; BGP não é ativado explicitamente. MTU segue o valor do manifest; ajuste manual se a rede tiver overhead de túnel.

## O que o Calico resolve na nossa arquitetura
- Rede pod-pod e pod-service consistente sem depender de overlay complexo (modo padrão com IP-in-IP somente se necessário pelo cluster).
- Isolamento entre workloads via NetworkPolicy: default-deny nos namespaces de apps e liberação apenas do que é necessário.
- Controle de egress: liberar apenas workloads aprovados para internet com label (`networking.raijin.dev/egress=internet`), reduzindo superfícies de exfiltração.
- Compatibilidade com ambientes bare metal/VM simples, sem exigir hardware de rede específico.

## Como operamos
- Health: `kubectl get pods -n kube-system -l k8s-app=calico-node` e `kubectl get ds calico-node -n kube-system`.
- IP pools/estado: `kubectl get ippools.crd.projectcalico.org` e `kubectl get ippools -o yaml` para conferir o CIDR aplicado.
- Policies padrão: `kubectl get networkpolicy -A | grep default-deny` e `kubectl get networkpolicy -A | grep allow-egress-internet`.
- Liberação de egress por label: listar workloads sem label em `apps` com `kubectl get deploy,statefulset,daemonset -n apps -o json | jq -r '.items[] | select(.metadata.labels["networking.raijin.dev/egress"]!="internet") | .metadata.name'`.
- Ajustar MTU se necessário: editar ConfigMap `calico-config` em `kube-system` (campo `veth_mtu`) quando houver túnel/VPN causando fragmentação.

## Manutenção e monitoramento
- Atualizações: seguir a versão de manifest referenciada; testar em ambiente de staging antes de aplicar em produção. Evitar quebrar o Pod CIDR ao atualizar.
- Saúde contínua: monitorar o DaemonSet `calico-node` (Ready/NotReady) e métricas via Prometheus se disponíveis (calico-node-exporter opcional).
- Logs: `kubectl logs -n kube-system -l k8s-app=calico-node`; observar mensagens de felix para drops e MTU issues.
- Drift de políticas: revisar NetworkPolicies aplicadas nos namespaces de apps para garantir default-deny + allow necessários.
- CIDR/IPPools: evitar alterações disruptivas; se mudar pod CIDR, reprovisione o cluster ou siga playbook de migração.
- MTU: verificar se há fragmentação/timeouts em conexões longas; ajustar `veth_mtu` no ConfigMap `calico-config` se a underlay usar VPN/túneis.

## Troubleshooting
- Ver eventos de pods afetados: `kubectl describe pod <nome> -n <ns>` (procure deny/NetworkPolicy).
- Temporário: aplicar uma NetworkPolicy de allow para validar se o problema é bloqueio de rede.
- Logs calico-node: `kubectl logs -n kube-system -l k8s-app=calico-node`.
- Conectividade pod-pod: `kubectl exec -it <pod> -n <ns> -- ping <ip/pod>`.
- Egress não sai: confirmar label `networking.raijin.dev/egress=internet` no workload e existência da policy `allow-egress-internet` no namespace.
- CIDR incorreto: re-aplicar Calico com o Pod CIDR correto ou ajuste no IPPool seguindo a documentação oficial.

## Links úteis
- https://docs.tigera.io/

---

## Glossário

### 1. CNI
**CNI** (Container Network Interface): Plugin que configura rede para containers (IPs, rotas, interfaces).
- **[Documentação oficial](https://github.com/containernetworking/cni)**

### 2. NetworkPolicy
**NetworkPolicy**: Recurso Kubernetes que define regras de firewall L3/L4 para pods.
- **[Spec Kubernetes](https://kubernetes.io/docs/concepts/services-networking/network-policies/)**

### 3. L3
**L3** (Layer 3): Camada de rede do modelo OSI (endereçamento IP).

### 4. L4
**L4** (Layer 4): Camada de transporte (TCP/UDP, portas).

### 5. Service Mesh
**Service Mesh**: Camada de infraestrutura (ex.: Istio) para controle avançado de tráfego L7; Calico opera em L3/L4.

### 6. BGP
**BGP** (Border Gateway Protocol): Protocolo de roteamento usado pelo Calico em modo avançado (não ativo no Raijin V1).
- **[RFC 4271](https://datatracker.ietf.org/doc/html/rfc4271)**

### 7. IP-in-IP
**IP-in-IP**: Encapsulamento de pacotes IP para roteamento entre nodes (usado por Calico quando necessário).

### 8. MTU
**MTU** (Maximum Transmission Unit): Tamanho máximo de pacote na rede; deve ser ajustado se houver túneis/VPN.

### 9. CIDR
**CIDR** (Classless Inter-Domain Routing): Notação de bloco IP (ex.: 10.244.0.0/16).
- **[RFC 4632](https://datatracker.ietf.org/doc/html/rfc4632)**

### 10. IPPool
**IPPool**: Recurso do Calico que define o range de IPs alocáveis para pods.

---

## Exemplos práticos

### Criar NetworkPolicy básica (allow ingress de namespace específico)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-from-frontend
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: frontend
    ports:
    - protocol: TCP
      port: 8080
```

### Aplicar e testar

```bash
kubectl apply -f networkpolicy.yaml
# Testar conexão de pod no namespace frontend
kubectl exec -n frontend -it frontend-pod -- curl http://backend.apps.svc:8080
```

### Verificar políticas aplicadas em um pod

```bash
kubectl describe pod <pod-name> -n apps
kubectl get networkpolicy -n apps
```

### Listar pods sem label de egress restrito

```bash
kubectl get deploy,statefulset -n apps -o json | \
  jq -r '.items[] | select(.metadata.labels["networking.raijin.dev/egress"]!="internet") | .metadata.name'
```

---

## Boas práticas ✅

1. **Default-deny primeiro**: Sempre começar com política `default-deny-all` no namespace e liberar apenas o necessário.
2. **Namespaces isolados**: Criar namespaces separados por ambiente (apps, staging, monitoring) com policies específicas.
3. **Labels consistentes**: Usar labels padronizados para identificar workloads (`app`, `tier`, `networking.raijin.dev/egress`).
4. **Documentar policies**: Manter YAML versionado com comentários explicando cada regra.
5. **Testar antes de aplicar**: Validar policies em ambiente de teste antes de produção.
6. **Egress explícito**: Não liberar `0.0.0.0/0` para todos; usar labels para marcar workloads que precisam de internet.
7. **Monitorar drops**: Configurar alertas para detectar tráfego bloqueado inesperado (logs do calico-node).
8. **MTU adequado**: Ajustar MTU se houver VPN/túnel (padrão 1500; túneis geralmente requerem 1450 ou menos).
9. **Revisar IPPool**: Garantir que Pod CIDR não conflita com rede da underlay.
10. **Backup de policies**: Versionar todas as NetworkPolicies em Git.

---

## Práticas ruins ❌

1. **Sem default-deny**: Deixar namespace sem policy padrão expõe todos os pods.
2. **Allow 0.0.0.0/0 indiscriminado**: Liberar egress para internet sem critério aumenta superfície de exfiltração.
3. **Policies muito amplas**: Usar `podSelector: {}` (todos pods) em ingress/egress quando não necessário.
4. **Não testar policies**: Aplicar em produção sem validar pode causar outages.
5. **Ignorar logs**: Não monitorar logs do calico-node pode esconder bloqueios legítimos.
6. **Alterar Pod CIDR em cluster ativo**: Mudar CIDR exige reprovisionar cluster; não faça em produção sem plano de migração.
7. **MTU incorreto**: Não ajustar MTU com túnel causa fragmentação e timeouts intermitentes.
8. **Labels inconsistentes**: Usar labels diferentes entre workloads dificulta aplicação de policies.
9. **Não versionar policies**: Perder histórico de mudanças em NetworkPolicies complica troubleshooting.
10. **Sobrepor policies conflitantes**: Criar múltiplas policies sem coordenação pode gerar comportamento inesperado.

---

## Diagnóstico avançado

### Verificar conectividade pod-to-pod

```bash
# Pegar IP do pod destino
kubectl get pod <target-pod> -n <ns> -o jsonpath='{.status.podIP}'

# Testar de outro pod
kubectl exec -n <source-ns> -it <source-pod> -- ping <target-ip>
kubectl exec -n <source-ns> -it <source-pod> -- curl http://<target-ip>:8080
```

### Ver eventos de NetworkPolicy

```bash
kubectl get events -n apps --sort-by='.lastTimestamp' | grep NetworkPolicy
```

### Logs detalhados do calico-node (felix)

```bash
kubectl logs -n kube-system -l k8s-app=calico-node | grep -i deny
kubectl logs -n kube-system -l k8s-app=calico-node | grep -i drop
```

### Inspecionar IPPool e CIDR ativo

```bash
kubectl get ippools.crd.projectcalico.org -o yaml
kubectl get nodes -o jsonpath='{.items[*].spec.podCIDR}'
```

### Verificar status do DaemonSet

```bash
kubectl get ds calico-node -n kube-system
kubectl rollout status ds/calico-node -n kube-system
```

### Ajustar MTU em runtime (temporário)

```bash
kubectl edit cm calico-config -n kube-system
# Alterar veth_mtu para 1450 (exemplo)
kubectl rollout restart ds/calico-node -n kube-system
```

### Validar policy com dry-run

```bash
kubectl apply -f networkpolicy.yaml --dry-run=client -o yaml
```

---

**[← Voltar ao Índice](README.md)** | **[Próximo: Cert-Manager →](cert-manager.md)**
