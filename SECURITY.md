# Politica de Seguranca (resumida)

## Hardening aplicado pelo CLI
- `fail2ban`, `unattended-upgrades`, `auditd` e sysctls de rede seguros.
- UFW com portas basicas (22/80/443/6443/etcd/kubelet) e reset inicial.
- Netplan para IP fixo e DNS; containerd com SystemdCgroup; kubeadm com RBAC habilitado.
- Calico com CIDR customizado e NetworkPolicy default-deny.

## Recomendacoes pos-instalacao
- Trocar senhas default, remover chaves temporarias e revisar usuarios sudoers.
- Habilitar 2FA/SSH com chaves, desabilitar senha em SSH e restringir IPs de gerenciamento.
- Configurar backups do Velero com rotacao e testes de restore; criptografar segredos (SealedSecrets/External Secrets).
- Revisar ingress (Traefik/Kong) com TLS valido, listas de IP de origem e rate limit.
- Monitorar com Prometheus/Grafana/Alertmanager e acionar alertas para login suspeito, CPU/IO anormais e erros de API server.

## Reporte de vulnerabilidades
- Use canal privado (email de seguranca ou issue privada). Evite divulgar PoCs publicamente antes do patch.

## Referencias
- Guia oficial de seguranca do Ubuntu: https://ubuntu.com/security
- CIS Benchmark para Ubuntu: https://www.cisecurity.org/benchmark/ubuntu_linux
