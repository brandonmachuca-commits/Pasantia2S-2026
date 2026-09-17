#!/bin/bash
# ══════════════════════════════════════════════════════
#   Asistente Virtual IA — Script de inicio
# ══════════════════════════════════════════════════════
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Asistente Virtual IA"
echo "══════════════════════════════════════════════════════"

cd "$DIR"

# Virtual environment
if [ ! -d "venv" ]; then
  echo "  Creando entorno virtual Python…"
  python3 -m venv venv
fi

source venv/bin/activate

echo "  Instalando/verificando dependencias…"
pip install -q -r backend/requirements.txt

echo ""
echo "  Servidor: http://localhost:9014"
echo "  Abre esa URL en tu navegador."
echo "  Presiona Ctrl+C para detener."
echo "══════════════════════════════════════════════════════"
echo ""

python backend/main.py
