#!/bin/bash
# Quick Docker verification for OpenSplit Infrastructure

echo "🔍 Verificando Docker..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker no instalado"
    exit 1
fi

# Check Docker daemon
if ! docker ps &> /dev/null; then
    echo "❌ Docker daemon no corriendo o sin permisos"
    echo "   Ejecuta: newgrp docker"
    echo "   O haz logout/login"
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose (plugin) no disponible"
    exit 1
fi

echo "✅ Docker instalado: $(docker --version)"
echo "✅ Docker Compose: $(docker compose version --short)"
echo "✅ Docker daemon corriendo"
echo ""
echo "🚀 Listo para levantar el stack:"
echo "   cd /path/to/OpenSplit"
echo "   ./scripts/setup.sh"
