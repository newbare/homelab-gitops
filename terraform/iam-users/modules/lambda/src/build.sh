#!/bin/bash
# ============================================
# build.sh — Empacota a Lambda com dependências
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔨 Build da Lambda..."

# Limpa builds antigos
rm -rf package lambda.zip
mkdir -p package

# Instala dependências no package/
echo "📦 Instalando dependências..."
pip install -r requirements.txt -t package/ --quiet

# Copia o handler
cp handler.py package/

# Cria o ZIP
echo "🗜️  Criando lambda.zip..."
cd package
zip -r ../lambda.zip . -x "*.pyc" "__pycache__/*" -q
cd ..

echo "✅ lambda.zip criado: $(ls -lh lambda.zip | awk '{print $5}')"
