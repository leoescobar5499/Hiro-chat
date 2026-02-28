#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# INSTALL.SH — Instalación de Hiro Chat
# Uso: bash install.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e

VENV_DIR="./venv"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

# ── Colores ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       Hiro Chat — Instalador         ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Verificar Python ────────────────────────────────────────────────────
echo -e "${YELLOW}▶ Verificando Python...${NC}"

PYTHON_BIN=""
for bin in python3 python; do
    if command -v "$bin" &>/dev/null; then
        VERSION=$("$bin" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge "$PYTHON_MIN_MAJOR" ] && [ "$MINOR" -ge "$PYTHON_MIN_MINOR" ]; then
            PYTHON_BIN="$bin"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}✗ Se requiere Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} o superior.${NC}"
    echo -e "  Instalalo con: sudo apt install python3"
    exit 1
fi

echo -e "${GREEN}✓ Python encontrado: $($PYTHON_BIN --version)${NC}"

# ── 2. Verificar pip ───────────────────────────────────────────────────────
echo -e "${YELLOW}▶ Verificando pip...${NC}"
if ! "$PYTHON_BIN" -m pip --version &>/dev/null; then
    echo -e "${RED}✗ pip no encontrado.${NC}"
    echo -e "  Instalalo con: sudo apt install python3-pip"
    exit 1
fi
echo -e "${GREEN}✓ pip disponible${NC}"

# ── 3. Crear entorno virtual ───────────────────────────────────────────────
echo -e "${YELLOW}▶ Creando entorno virtual en ./venv ...${NC}"
"$PYTHON_BIN" -m venv "$VENV_DIR"
echo -e "${GREEN}✓ Entorno virtual creado${NC}"

# ── 4. Instalar dependencias ───────────────────────────────────────────────
echo -e "${YELLOW}▶ Instalando dependencias desde requirements.txt ...${NC}"

if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ No se encontró requirements.txt en el directorio actual.${NC}"
    echo -e "  Asegurate de correr este script desde la carpeta del proyecto."
    exit 1
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r requirements.txt

echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# ── 5. Crear carpetas necesarias ───────────────────────────────────────────
echo -e "${YELLOW}▶ Creando estructura de carpetas...${NC}"
mkdir -p data/personajes/hiro
mkdir -p backups
mkdir -p static
echo -e "${GREEN}✓ Carpetas listas${NC}"

# ── 6. Copiar archivos de configuración de ejemplo ────────────────────────
echo -e "${YELLOW}▶ Configurando archivos iniciales...${NC}"

copy_if_missing() {
    local src="$1"
    local dst="$2"
    if [ ! -f "$dst" ]; then
        cp "$src" "$dst"
        echo -e "${GREEN}  ✓ Creado: $dst${NC}"
    else
        echo -e "  · Ya existe: $dst (no se sobreescribe)"
    fi
}

copy_if_missing "data/api_config.example.json"      "data/api_config.json"
copy_if_missing "data/libreria_modelos.example.json" "data/libreria_modelos.json"
copy_if_missing "data/modelos_activos.example.json"  "data/modelos_activos.json"
copy_if_missing "data/personaje_activo.example.json" "data/personaje_activo.json"

# ── 7. Archivo .env ────────────────────────────────────────────────────────
copy_if_missing ".env.example" ".env"

# ── 8. Hacer ejecutable el script de arranque ──────────────────────────────
if [ -f "run_app.sh" ]; then
    chmod +x run_app.sh
    echo -e "${GREEN}✓ run_app.sh marcado como ejecutable${NC}"
fi

# ── Listo ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        ✓ Instalación completa        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${YELLOW}⚠️  Antes de iniciar:${NC}"
echo -e "  Configurá al menos una API key en la app o editando:"
echo -e "  ${CYAN}data/api_config.json${NC}"
echo ""
echo -e "  Para iniciar la app:"
echo -e "  ${CYAN}bash run_app.sh${NC}"
echo ""
