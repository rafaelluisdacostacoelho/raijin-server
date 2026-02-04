# MetalLB — LoadBalancer para Bare Metal

> **Navegação**: [← Voltar ao Índice](README.md) | [← Anterior: Helm](helm.md) | [Próximo: Bootstrap →](bootstrap.md)

---

## Índice
- [O que é](#o-que-é)
- [Por que usamos](#por-que-usamos)
- [Como está configurado (V1)](#como-está-configurado-no-raijin-v1)
- [Operação](#como-operamos)
- [Manutenção](#manutenção)
- [Troubleshooting](#troubleshooting)
- [Glossário](#glossário)
- [Exemplos práticos](#exemplos-práticos)
- [Boas práticas](#boas-práticas-)
- [Práticas ruins](#práticas-ruins-)
- [Diagnóstico avançado](#diagnóstico-avançado)

---

## O que é
- **[MetalLB](#1-metallb)¹** é um **[Load Balancer](#2-load-balancer)²** para clusters Kubernetes em **[bare-metal](#3-bare-metal)³**.
- Permite usar **[Services](#4-service)⁴** do tipo `LoadBalancer` sem cloud provider (AWS/GCP/Azure).
- Dois modos: **[Layer 2](#5-layer-2-mode)⁵** (ARP/NDP) e **[BGP](#6-bgp-mode)⁶** (roteamento).

## Por que usamos
- **Bare-metal**: Clusters on-premises não têm ELB/NLB nativo.
- **IP externo real**: Services LoadBalancer recebem IPs acessíveis fora do cluster.
- **Traefik/Istio**: Ingress Controllers precisam de LoadBalancer para exposição.
- **Alternativa ao NodePort**: Evita portas altas (30000-32767) e múltiplos IPs.

## Como está configurado no Raijin (V1)
- **Versão**: MetalLB 0.14+ (via manifest oficial)
- **Namespace**: `metallb-system`
- **Modo**: **Layer 2** (default para simplicidade)
- **Pool de IPs**: Range definido via `IPAddressPool` (ex.: `192.168.1.240-192.168.1.250`)
- **CRDs**:
  - `IPAddressPool`: Define ranges de IPs disponíveis
  - `L2Advertisement`: Anuncia IPs via ARP/NDP
- **Integração**: Usado por Traefik, Istio, Kong (quando instalados)

## Como operamos

### Ver configuração

```bash
# Pods do MetalLB
kubectl get pods -n metallb-system

# ConfigMaps e secrets
kubectl get cm,secrets -n metallb-system

# CRDs
kubectl get ipaddresspools,l2advertisements -n metallb-system

# Pool de IPs
kubectl get ipaddresspool -n metallb-system -o yaml
```

### Services com LoadBalancer

```bash
# Listar services LoadBalancer
kubectl get svc -A | grep LoadBalancer

# Ver IP externo atribuído
kubectl get svc traefik -n traefik
# NAME      TYPE           CLUSTER-IP      EXTERNAL-IP      PORT(S)
# traefik   LoadBalancer   10.96.123.45    192.168.1.240    80:32080/TCP,443:32443/TCP

# Testar conectividade
curl http://192.168.1.240
```

### Adicionar IP pool

```bash
# Criar novo pool
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: production-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.1.240-192.168.1.250
  autoAssign: true
EOF

# Criar advertisement Layer 2
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: production-l2
  namespace: metallb-system
spec:
  ipAddressPools:
  - production-pool
EOF
```

## Manutenção

### Expandir pool de IPs

```bash
# Editar IPAddressPool existente
kubectl edit ipaddresspool <pool-name> -n metallb-system

# Exemplo: adicionar novo range
spec:
  addresses:
  - 192.168.1.240-192.168.1.250
  - 192.168.1.100-192.168.1.110  # Novo range
```

### Reservar IP específico

```bash
# Service com IP fixo
apiVersion: v1
kind: Service
metadata:
  name: traefik
  namespace: traefik
  annotations:
    metallb.universe.tf/loadBalancerIPs: 192.168.1.240
spec:
  type: LoadBalancer
  ports:
  - port: 80
  selector:
    app: traefik
```

### Migração Layer 2 → BGP

```bash
# 1. Instalar BGP speaker (calico/frr)
# 2. Criar BGPPeer
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta2
kind: BGPPeer
metadata:
  name: router-peer
  namespace: metallb-system
spec:
  myASN: 64500
  peerASN: 64501
  peerAddress: 192.168.1.1
EOF

# 3. Criar BGPAdvertisement
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: BGPAdvertisement
metadata:
  name: bgp-adv
  namespace: metallb-system
spec:
  ipAddressPools:
  - production-pool
EOF
```

## Troubleshooting

### Service sem EXTERNAL-IP

```bash
# Verificar pods MetalLB
kubectl get pods -n metallb-system

# Logs do controller
kubectl logs -n metallb-system -l app=metallb,component=controller

# Verificar IPAddressPool
kubectl get ipaddresspool -n metallb-system -o yaml

# Verificar se pool tem IPs disponíveis
kubectl describe ipaddresspool <pool-name> -n metallb-system
```

### IP não acessível externamente (Layer 2)

```bash
# Verificar L2Advertisement
kubectl get l2advertisement -n metallb-system -o yaml

# Verificar ARP cache no node
kubectl get nodes -o wide
ssh <node-ip>
ip neigh show

# Testar ping do IP
ping 192.168.1.240

# Verificar logs do speaker
kubectl logs -n metallb-system -l app=metallb,component=speaker
```

### Conflito de IP (dois services com mesmo IP)

```bash
# Listar IPs atribuídos
kubectl get svc -A -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.name}{"\t"}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}'

# Liberar IP (delete service antigo)
kubectl delete svc <old-service> -n <namespace>

# Forçar reassign
kubectl annotate svc <service> -n <namespace> metallb.universe.tf/loadBalancerIPs-
kubectl annotate svc <service> -n <namespace> metallb.universe.tf/loadBalancerIPs=192.168.1.241
```

## Glossário

### 1. MetalLB
**MetalLB**: Implementação de Load Balancer para Kubernetes bare-metal; aloca IPs externos para Services tipo LoadBalancer.
- **[metallb.universe.tf](https://metallb.universe.tf/)**

### 2. Load Balancer
**Load Balancer**: Distribui tráfego de rede entre múltiplos backends (pods/nodes).

### 3. Bare-metal
**Bare-metal**: Servidores físicos ou VMs sem cloud provider (AWS/GCP/Azure).

### 4. Service
**Service**: Abstração Kubernetes que expõe um conjunto de pods como endpoint de rede.

### 5. Layer 2 Mode
**Layer 2 Mode**: Modo MetalLB que usa ARP/NDP para anunciar IPs na rede local (simples, sem BGP).

### 6. BGP Mode
**BGP Mode**: Modo MetalLB que usa Border Gateway Protocol para roteamento (escalável, multi-site).
- **[BGP RFC 4271](https://datatracker.ietf.org/doc/html/rfc4271)**

### 7. IPAddressPool
**IPAddressPool**: CRD que define ranges de IPs disponíveis para alocação (ex.: `192.168.1.240-250`).

### 8. L2Advertisement
**L2Advertisement**: CRD que configura anúncio Layer 2 (ARP) para pools de IPs.

### 9. BGPAdvertisement
**BGPAdvertisement**: CRD que configura anúncio BGP para pools de IPs.

### 10. Speaker
**Speaker**: Pod MetalLB que roda em cada node e anuncia IPs (Layer 2 ou BGP).

---

## Exemplos práticos

### IPAddressPool básico

```yaml
# ipaddresspool.yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.1.240-192.168.1.250  # 11 IPs disponíveis
  autoAssign: true  # Atribuir automaticamente
```

### L2Advertisement

```yaml
# l2advertisement.yaml
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default-l2
  namespace: metallb-system
spec:
  ipAddressPools:
  - default-pool
  # nodeSelectors: []  # Opcional: restringir a nodes específicos
```

### Service LoadBalancer

```yaml
# traefik-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: traefik
  namespace: traefik
spec:
  type: LoadBalancer
  selector:
    app: traefik
  ports:
  - name: http
    port: 80
    targetPort: 8080
  - name: https
    port: 443
    targetPort: 8443
  # IP será atribuído automaticamente do pool
```

### Service com IP fixo

```yaml
# traefik-fixed-ip.yaml
apiVersion: v1
kind: Service
metadata:
  name: traefik
  namespace: traefik
  annotations:
    metallb.universe.tf/loadBalancerIPs: 192.168.1.240
spec:
  type: LoadBalancer
  loadBalancerIP: 192.168.1.240  # Deprecated mas ainda funciona
  selector:
    app: traefik
  ports:
  - name: http
    port: 80
```

### Pool com múltiplos ranges

```yaml
# multi-range-pool.yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: multi-range-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.1.240-192.168.1.250  # Range 1
  - 10.0.0.100-10.0.0.110        # Range 2 (outra subnet)
  - 172.16.50.10/32              # IP único
  autoAssign: true
```

### BGP Mode

```yaml
# bgppeer.yaml
apiVersion: metallb.io/v1beta2
kind: BGPPeer
metadata:
  name: router
  namespace: metallb-system
spec:
  myASN: 64500      # ASN do cluster
  peerASN: 64501    # ASN do router
  peerAddress: 192.168.1.1
  # holdTime: 120s
  # routerID: 192.168.1.2

---
# bgpadvertisement.yaml
apiVersion: metallb.io/v1beta1
kind: BGPAdvertisement
metadata:
  name: bgp-adv
  namespace: metallb-system
spec:
  ipAddressPools:
  - default-pool
  # aggregationLength: 32  # /32 por IP
  # localPref: 100
```

---

## Boas práticas ✅

1. **Pool reservado**: Separar IPs do pool da rede DHCP.
2. **Documentar ranges**: Comentar quais IPs são para qual serviço.
3. **autoAssign: false para produção**: Forçar IPs fixos via annotation.
4. **L2 para single-site**: Usar Layer 2 em clusters single-datacenter.
5. **BGP para multi-site**: Usar BGP em clusters distribuídos.
6. **Monitorar IPs livres**: Alertar quando pool estiver 80% usado.
7. **Testar failover**: Validar que IP migra entre nodes em falhas.
8. **Firewall externo**: Restringir acesso aos IPs do pool.
9. **HA nodes**: Garantir que speaker roda em múltiplos nodes.
10. **Namespace dedicado**: Manter MetalLB em `metallb-system`.
11. **CRDs versionados**: Usar `v1beta1` (não `v1alpha1`).
12. **Labels em pools**: Organizar pools por ambiente (prod/staging).
13. **Evitar overlaps**: Garantir que ranges não se sobrepõem.
14. **Logs centralizados**: Enviar logs do speaker para Loki.
15. **Validar ARP**: Testar que IPs respondem a `arping`.

---

## Práticas ruins ❌

1. **Pool DHCP compartilhado**: Conflito de IPs com dispositivos da rede.
2. **Range gigante**: Desperdiçar IPs (ex.: /24 inteiro).
3. **autoAssign sem limites**: Esgotar pool rapidamente.
4. **Sem reserva de IP**: Services com IP aleatório dificultam DNS.
5. **BGP sem redundância**: Único peer BGP = SPOF.
6. **L2 em multi-site**: Não funciona entre datacenters.
7. **IP fora do pool**: Configurar `loadBalancerIP` que não está no range.
8. **Firewall bloqueando ARP**: Speaker não consegue anunciar IP.
9. **Speaker em node único**: Failover não funciona.
10. **CRDs antigos**: Usar `ConfigMap` em vez de `IPAddressPool`.
11. **Sem monitoramento**: Não saber quando pool estiver cheio.
12. **Delete de IPAddressPool em uso**: Quebra Services ativos.
13. **Múltiplos L2Advertisement**: Causar flapping de ARP.
14. **BGP sem holdTime**: Sessões instáveis em redes lentas.
15. **IP público em bare-metal**: Expor IPs públicos sem firewall.

---

## Diagnóstico avançado

### Verificar IPs alocados

```bash
# Ver todos IPs LoadBalancer
kubectl get svc -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip' | grep LoadBalancer

# Contar IPs usados
kubectl get svc -A -o json | jq '[.items[] | select(.spec.type=="LoadBalancer") | .status.loadBalancer.ingress[0].ip] | length'
```

### Logs do controller

```bash
# Controller decide alocação de IPs
kubectl logs -n metallb-system -l app=metallb,component=controller --tail=100 -f

# Procurar erros
kubectl logs -n metallb-system -l app=metallb,component=controller | grep -i error
```

### Logs do speaker

```bash
# Speaker anuncia IPs via ARP/BGP
kubectl logs -n metallb-system -l app=metallb,component=speaker --tail=100 -f

# Ver announcements
kubectl logs -n metallb-system -l app=metallb,component=speaker | grep announce
```

### Testar ARP (Layer 2)

```bash
# No host externo
arping -I eth0 192.168.1.240

# Ver tabela ARP
arp -a | grep 192.168.1.240

# Limpar cache ARP
sudo ip neigh flush all
```

### Testar BGP

```bash
# Ver sessões BGP (se usando Calico)
calicoctl node status

# Ver rotas BGP
kubectl exec -n kube-system <calico-node-pod> -- ip route show

# Logs BGP peer
kubectl logs -n metallb-system -l app=metallb,component=speaker | grep bgp
```

### Forçar reassign de IP

```bash
# Delete e recria service
kubectl delete svc <service> -n <namespace>
kubectl apply -f <service>.yaml

# Ou force annotation
kubectl annotate svc <service> -n <namespace> metallb.universe.tf/loadBalancerIPs- --overwrite
kubectl annotate svc <service> -n <namespace> metallb.universe.tf/loadBalancerIPs=192.168.1.241
```

### Validar configuração

```bash
# Ver status do IPAddressPool
kubectl describe ipaddresspool -n metallb-system

# Ver events
kubectl get events -n metallb-system --sort-by='.lastTimestamp'

# Verificar se speaker está em todos os nodes
kubectl get pods -n metallb-system -o wide
```

---

**[← Voltar ao Índice](README.md)** | **[← Anterior: Helm](helm.md)** | **[Próximo: Bootstrap →](bootstrap.md)**
