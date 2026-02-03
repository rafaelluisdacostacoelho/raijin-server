# Calico (CNI e Network Policy)

## O que é
- CNI que provê rede pod-pod, roteamento e NetworkPolicies.
- Mantemos modo padrão com políticas habilitadas e default-deny nos namespaces de apps.

## Por que usamos
- NetworkPolicies granulares (L3/L4) para isolar workloads.
- Estável e amplamente usado em clusters bare metal.

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
