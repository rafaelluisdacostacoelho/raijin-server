#!/bin/bash
set -e

echo "============================================"
echo "  Security Check — Monorepo App"
echo "============================================"
echo ""

ERRORS=0
WARNINGS=0

check_pass() { echo "  ✓ $1"; }
check_warn() { echo "  ⚠ $1"; WARNINGS=$((WARNINGS+1)); }
check_fail() { echo "  ✗ $1"; ERRORS=$((ERRORS+1)); }

# ---------- Go API ----------
echo "[Go API]"

if grep -q 'net/http' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "Usando stdlib net/http (sem deps desnecessárias)"
else
  check_warn "Verificar framework HTTP usado"
fi

if grep -q 'bcrypt' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "Bcrypt para hashing de senhas"
else
  check_fail "Hashing de senhas não encontrado"
fi

if grep -q 'X-CSRF-Token' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "Proteção CSRF implementada"
else
  check_fail "CSRF não configurado"
fi

if grep -q 'Strict-Transport-Security' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "HSTS header configurado"
else
  check_fail "HSTS não encontrado"
fi

if grep -q 'Content-Security-Policy' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "CSP header configurado"
else
  check_warn "CSP não encontrado no backend"
fi

if grep -q 'RateLimiter' backends/api-go/cmd/server/main.go 2>/dev/null; then
  check_pass "Rate limiting implementado"
else
  check_fail "Rate limiting não encontrado"
fi

echo ""

# ---------- Frontend ----------
echo "[Frontend — React]"

if grep -q 'DOMPurify\|dompurify' frontends/meu-app-web/src/lib/api.ts 2>/dev/null; then
  check_pass "DOMPurify para sanitização XSS"
else
  check_fail "Sanitização XSS não encontrada"
fi

if grep -q 'X-CSRF-Token' frontends/meu-app-web/src/lib/api.ts 2>/dev/null; then
  check_pass "CSRF token enviado nas requisições"
else
  check_fail "CSRF token não enviado pelo frontend"
fi

if ! grep -rq 'localStorage.*token\|sessionStorage.*token' frontends/meu-app-web/src/ 2>/dev/null; then
  check_pass "Tokens NÃO armazenados em localStorage/sessionStorage"
else
  check_fail "Tokens expostos em localStorage/sessionStorage"
fi

echo ""

# ---------- Nginx ----------
echo "[Nginx]"

if grep -q 'X-Frame-Options' frontends/meu-app-web/nginx.conf 2>/dev/null; then
  check_pass "X-Frame-Options (clickjacking)"
else
  check_fail "X-Frame-Options ausente"
fi

if grep -q 'X-Content-Type-Options' frontends/meu-app-web/nginx.conf 2>/dev/null; then
  check_pass "X-Content-Type-Options (MIME sniffing)"
else
  check_fail "X-Content-Type-Options ausente"
fi

if grep -q 'proxy_pass.*api-go' frontends/meu-app-web/nginx.conf 2>/dev/null; then
  check_pass "Same-origin proxy (CORS eliminado em produção)"
else
  check_warn "Proxy reverso não configurado"
fi

echo ""

# ---------- Docker ----------
echo "[Docker]"

for svc in api-go api-python api-dotnet; do
  if [ -f "backends/${svc}/Dockerfile" ]; then
    if grep -q 'USER\|--chown' "backends/${svc}/Dockerfile" 2>/dev/null; then
      check_pass "${svc}: Container roda como non-root"
    else
      check_warn "${svc}: Verificar user no container"
    fi
  fi
done

if [ -f "frontends/meu-app-web/Dockerfile" ]; then
  if grep -q 'USER\|chown' frontends/meu-app-web/Dockerfile 2>/dev/null; then
    check_pass "meu-app-web: Container roda como non-root"
  else
    check_warn "meu-app-web: Verificar user no container"
  fi
fi

echo ""

# ---------- Kubernetes ----------
echo "[Kubernetes]"

if grep -q 'ExternalSecret' kubernetes/base/externalsecrets.yaml 2>/dev/null; then
  check_pass "ExternalSecrets configurado (sem secrets em YAML)"
else
  check_warn "ExternalSecrets não encontrado"
fi

if grep -q 'PodDisruptionBudget' kubernetes/overlays/prd/pdb.yaml 2>/dev/null; then
  check_pass "PDB configurado para produção"
else
  check_warn "PDB não encontrado"
fi

if grep -q 'HorizontalPodAutoscaler' kubernetes/overlays/prd/hpa.yaml 2>/dev/null; then
  check_pass "HPA configurado para produção"
else
  check_warn "HPA não encontrado"
fi

echo ""

# ---------- CI/CD ----------
echo "[CI/CD]"

if grep -q 'semgrep\|Semgrep' .github/workflows/ci-tst.yml 2>/dev/null; then
  check_pass "SAST (Semgrep) no pipeline TST"
else
  check_warn "SAST não encontrado no TST"
fi

if grep -q 'trivy\|Trivy' .github/workflows/ci-prd.yml 2>/dev/null; then
  check_pass "Container scanning (Trivy) no pipeline PRD"
else
  check_warn "Container scanning não encontrado"
fi

echo ""
echo "============================================"
echo "  Resultado: ${ERRORS} erros, ${WARNINGS} avisos"
echo "============================================"

if [ $ERRORS -gt 0 ]; then
  echo "  Corrija os erros acima antes de deployar."
  exit 1
fi

echo "  ✓ Segurança OK"
