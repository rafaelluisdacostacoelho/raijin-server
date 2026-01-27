# raijin-server

CLI em Python (Typer) para automatizar setup e hardening de servidores Ubuntu Server em ambientes produtivos. Orquestra rede, firewall, Kubernetes, observabilidade e backups para acelerar a subida de clusters e workloads.

## Requisitos

- Python >= 3.9
- Ubuntu Server com sudo/root
- Ferramentas usadas pelos modulos: `curl`, `helm` (>=3.8 para OCI), `kubectl`, `kubeadm`, `velero`, `istioctl` (instale conforme necessidade) e conectividade para os repositorios APT/Helm.

## Instalacao

Sem venv (global):

```bash
python -m pip install .
```

Com venv (recomendado para desenvolvimento):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Uso rapido

- Menu interativo: `raijin-server`
- Subcomandos diretos: `raijin-server hardening`, `raijin-server essentials`, `raijin-server kubernetes`, `raijin-server traefik`, etc.
- Versao: `raijin-server version`
- Dry-run (nao aplica, so mostra): `raijin-server --dry-run <modulo>`

## Estrutura

- `src/raijin_server/cli.py`: CLI principal com Typer, banner e `--dry-run`.
- `src/raijin_server/modules/`: automacoes por topico (hardening, network, essentials, firewall, kubernetes, calico, istio, traefik, kong, minio, prometheus, grafana, loki, harness, velero, kafka).
- `scripts/`: espaco para shells e templates.
- `ARCHITECTURE.md`: visao do desenho atual.
- `SECURITY.md`: como reportar e pensar seguranca.

## Modulos disponiveis

- `hardening`: fail2ban, unattended-upgrades, sysctl.
- `essentials`: pacotes base (curl, git, jq, etc.) e NTP.
- `network`: Netplan com IP fixo e DNS.
- `firewall`: UFW com regras para SSH/HTTP/HTTPS/K8s.
- `kubernetes`: kubeadm init, containerd SystemdCgroup, kubeconfig.
- `calico`: CNI Calico com CIDR custom e policy default-deny.
- `istio`: istioctl install (perfil raijin) e injeção automática.
- `traefik`: IngressController com TLS/ACME.
- `kong`: Ingress/Gateway com Helm.
- `minio`: armazenamento S3 compatível via Helm.
- `prometheus`, `grafana`, `loki`: observabilidade, dashboards e persistencia.
- `harness`: delegate Helm com parametros interativos.
- `velero`: backup/restore com schedule.
- `kafka`: deploy Bitnami via OCI.

## Roadmap basico

- Adicionar validacoes de pre-requisitos e health-check por modulo.
- Provisionar ingress seguro para Grafana/Prometheus/Alertmanager.
- Dashboards e alertas opinativos prontos para uso.
- Suporte a sealed-secrets/external-secrets para credenciais.
- Testes automatizados (pytest) e linters.

## Proximos passos sugeridos

- Substituir os stubs por comandos reais (apt, ufw, helm, kubectl, etc.).
- Adicionar validacoes e testes (por exemplo, pytest + testcontainers).
- Empacotar scripts auxiliares em `scripts/` e referencia-los nos modulos.
