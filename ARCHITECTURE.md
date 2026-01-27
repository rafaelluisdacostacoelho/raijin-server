# Arquitetura do ambiente (esperada)

## Visao macro (ASCII)

```
 [Users/CI/CD]
		|
	[Ingress]
 (Traefik/Kong) -- TLS/ACME, WAF, rate limit
		|
	[Service Mesh]
 Istio (mTLS, traffic split)
		|
  +---+------------+
  |                |
[Workloads]    [Data]
(Apps/Jobs)  (MinIO, Kafka)
  |                |
  +-------+--------+
			 |
	 [Observability]
 (Prometheus -> Grafana, Loki -> Grafana)
			 |
		 [Backup]
		  Velero
```

## Fluxo de provisao (CLI)

1. Sistema/base: `essentials`, `hardening`, `network`, `firewall`.
2. Cluster: `kubernetes` (kubeadm + containerd + kubeconfig).
3. Rede/CNI: `calico` (CIDR custom + default-deny).
4. Entrada: `traefik` ou `kong` (TLS/ACME, ingressClass).
5. Mallha/servicos: `istio` opcional.
6. Dados: `minio`, `kafka` via Helm/OCI.
7. Observabilidade: `prometheus`, `grafana`, `loki` (dashboards e datasources provisionados).
8. Backup: `velero` com schedule.
9. Add-ons CI/CD: `harness` delegate.

## Metodologia modular

- Cada modulo exposto como subcomando Typer (`raijin-server <modulo>`), com suporte a `--dry-run`.
- Idempotente na medida do possivel: repos, chaves GPG, namespaces e releases Helm reusam o estado existente.
- Placeholders prontos para extensao via `scripts/` (templates e shell helpers).
- Configuracao guiada por prompts (CIDR, ingress host, senhas admin, storage, tokens) para adaptar ao ambiente.

## Futuro/prioridades

- Health-check pos-provisionamento (smoke tests) por modulo.
- Gate de seguranca: sealed-secrets/external-secrets, policies (OPA/Gatekeeper ou Kyverno).
- Ingress seguro para observabilidade (Grafana/Alertmanager) com auth/IPS allowlist.
- Testes automatizados (pytest) e validacao de pre-requisitos (root, OS, conectividade, binarios).
