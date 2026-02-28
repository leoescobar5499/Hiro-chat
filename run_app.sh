#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# RUN_APP.SH — Arranque de Hiro Chat V4
# Uso: bash run_app.sh
# Se puede correr desde cualquier lugar — detecta su propia ubicación.
# ═══════════════════════════════════════════════════════════════════════════

# Directorio del proyecto = donde está este script (funciona desde cualquier ruta)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_FILE="app.py"

# ── Colores ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         Hiro Chat V4 — Inicio        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Verificar que estamos en el directorio correcto ────────────────────────
cd "$PROJECT_DIR" || { echo -e "${RED}✗ No se pudo acceder a: $PROJECT_DIR${NC}"; exit 1; }

# ── Verificar entorno virtual ──────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo -e "${RED}✗ Entorno virtual no encontrado en ./venv${NC}"
    echo -e "  Corré primero: ${CYAN}bash install.sh${NC}"
    exit 1
fi

# ── Verificar app.py ───────────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/$PYTHON_FILE" ]; then
    echo -e "${RED}✗ No se encontró $PYTHON_FILE en $PROJECT_DIR${NC}"
    exit 1
fi

# ── Activar venv y arrancar ────────────────────────────────────────────────
source "$VENV_DIR/bin/activate"

echo -e "${GREEN}✓ Entorno virtual activado${NC}"
echo -e "${GREEN}✓ Proyecto: $PROJECT_DIR${NC}"
echo ""
echo -e "  ${CYAN}Abrí http://localhost:5000 en tu navegador${NC}"
echo ""

python "$PYTHON_FILE"
