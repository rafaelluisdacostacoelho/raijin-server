#!/bin/bash
set -e

echo "============================================"
echo "  Monorepo App — Setup"
echo "============================================"
echo ""

# Verificar dependências
for cmd in docker kubectl; do
  if ! command -v $cmd &>/dev/null; then
    echo "ERRO: $cmd não encontrado. Instale antes de continuar."
    exit 1
  fi
done

echo "[1/4] Instalando dependências do frontend..."
if [ -d "frontends/meu-app-web" ]; then
  cd frontends/meu-app-web && npm install && cd ../..
fi

echo "[2/4] Baixando módulos Go..."
if [ -d "backends/api-go" ]; then
  cd backends/api-go && go mod download 2>/dev/null || echo "  (Go não instalado localmente — usando Docker)" && cd ../..
fi

echo "[3/4] Instalando dependências Python..."
if [ -d "backends/api-python" ]; then
  cd backends/api-python && pip install -e ".[dev]" 2>/dev/null || echo "  (Python não instalado localmente — usando Docker)" && cd ../..
fi

echo "[4/4] Subindo infraestrutura (postgres, redis, mailhog)..."
docker compose up -d postgres redis mailhog adminer

echo ""
echo "Aguardando PostgreSQL..."
until docker compose exec -T postgres pg_isready -U app -d appdb > /dev/null 2>&1; do
  sleep 1
done

echo ""
echo "============================================"
echo "  Setup completo!"
echo "============================================"
echo ""
echo "  Frontend (React):  http://localhost:5173"
echo "  API Go:            http://localhost:8080"
echo "  API Python:        http://localhost:8081"
echo "  API .NET:          http://localhost:8082"
echo "  MailHog:           http://localhost:8025"
echo "  Adminer:           http://localhost:8181"
echo ""
echo "  Comandos:"
echo "    make dev          — Subir tudo via Docker"
echo "    make dev-web      — Frontend local (hot reload)"
echo "    make dev-api      — API Go local + deps via Docker"
echo "    make logs         — Ver logs"
echo "    make help         — Todos os comandos"
echo ""
echo "  Demo login: admin@example.com / admin123"
echo ""
