#!/bin/bash
set -e

echo "============================================"
echo "  Vault + ExternalSecrets Setup"
echo "============================================"
echo ""
echo "Este script configura o Vault para uso com"
echo "ExternalSecrets Operator no Kubernetes."
echo ""

VAULT_ADDR="${VAULT_ADDR:-https://vault.infra.local}"
NAMESPACE="${1:-meu-app-tst}"
ENV="${2:-tst}"

echo "Vault:     $VAULT_ADDR"
echo "Namespace: $NAMESPACE"
echo "Env:       $ENV"
echo ""

# Verificar vault CLI
if ! command -v vault &>/dev/null; then
  echo "ERRO: vault CLI não encontrado"
  echo "  brew install vault  OU  https://developer.hashicorp.com/vault/install"
  exit 1
fi

echo "[1/5] Habilitando secrets engine kv-v2..."
vault secrets enable -path="apps/${ENV}/meu-app" kv-v2 2>/dev/null || true

echo "[2/5] Criando secrets..."

# API Go
vault kv put "apps/${ENV}/meu-app/api-go" \
  DATABASE_URL="postgres://app:secretpassword@postgres:5432/appdb?sslmode=require" \
  REDIS_URL="redis://:secretpassword@redis:6379/0" \
  JWT_SECRET="$(openssl rand -base64 48)" \
  CSRF_KEY="$(openssl rand -base64 32)" \
  ALLOWED_ORIGINS="https://app.${ENV}.example.com"

# API Python
vault kv put "apps/${ENV}/meu-app/api-python" \
  DATABASE_URL="postgres://app:secretpassword@postgres:5432/appdb?sslmode=require" \
  SECRET_KEY="$(openssl rand -base64 48)"

# API .NET
vault kv put "apps/${ENV}/meu-app/api-dotnet" \
  ConnectionStrings__Default="Host=postgres;Database=appdb;Username=app;Password=secretpassword" \
  Jwt__Secret="$(openssl rand -base64 48)"

echo "[3/5] Criando policy..."
vault policy write "meu-app-${ENV}" - <<EOF
path "apps/data/${ENV}/meu-app/*" {
  capabilities = ["read"]
}
path "apps/metadata/${ENV}/meu-app/*" {
  capabilities = ["read", "list"]
}
EOF

echo "[4/5] Configurando Kubernetes auth..."
vault auth enable kubernetes 2>/dev/null || true
vault write "auth/kubernetes/role/meu-app-${ENV}" \
  bound_service_account_names="external-secrets" \
  bound_service_account_namespaces="${NAMESPACE}" \
  policies="meu-app-${ENV}" \
  ttl=1h

echo "[5/5] Verificando..."
vault kv get "apps/${ENV}/meu-app/api-go" > /dev/null
echo "  ✓ Secrets criados com sucesso"

echo ""
echo "============================================"
echo "  Vault configurado para ${ENV}"
echo "============================================"
echo ""
echo "  Secrets path: apps/${ENV}/meu-app/"
echo "  Policy:       meu-app-${ENV}"
echo "  K8s role:     meu-app-${ENV}"
echo ""
echo "  Próximos passos:"
echo "    1. Deploy ExternalSecrets Operator no cluster"
echo "    2. kubectl apply -k kubernetes/overlays/${ENV}/"
echo "    3. Verificar: kubectl get externalsecrets -n ${NAMESPACE}"
echo ""
