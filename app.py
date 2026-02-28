# ═══════════════════════════════════════════════════════════════════════════
# APP.PY — Arranque y configuración
# Flask, _init_app(), backup_datos(), migrar_hiro_default(), blueprints.
# El archivo que tocás si cambia algo de infraestructura.
# ═══════════════════════════════════════════════════════════════════════════

import os, shutil
from datetime import datetime
from flask import Flask

from utils import PERSONAJES_DIR, get_personaje_activo_id
from memoria import cargar_personaje
from utils import init_database_personaje

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'hiro-chat-local-key-2024')

# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO DE BLUEPRINTS
# ─────────────────────────────────────────────────────────────────────────────

from routes import bp as main_bp
app.register_blueprint(main_bp)

try:
    from crear_personaje import crear_bp
    app.register_blueprint(crear_bp)
    print("✅ Blueprint crear_personaje registrado correctamente")
except Exception as _bp_err:
    print(f"❌ CRÍTICO: No se pudo registrar el blueprint crear_personaje: {_bp_err}")
    import traceback
    traceback.print_exc()
    raise


# ─────────────────────────────────────────────────────────────────────────────
# MIGRACIÓN LEGACY Y BACKUP
# ─────────────────────────────────────────────────────────────────────────────

def migrar_hiro_default():
    """Migra la DB legacy de Hiro a la nueva estructura multipersonaje. Corre una sola vez."""
    legacy_db   = './data/hiro.db'
    legacy_emb  = './data/embeddings.index'
    legacy_meta = './data/embeddings_metadata.msgpack'
    hiro_dir    = os.path.join(PERSONAJES_DIR, 'hiro')
    os.makedirs(hiro_dir, exist_ok=True)

    if os.path.exists(legacy_db) and not os.path.exists(os.path.join(hiro_dir, 'memoria.db')):
        shutil.copy2(legacy_db, os.path.join(hiro_dir, 'memoria.db'))
        print("✅ DB legacy migrada a ./data/personajes/hiro/")
    if os.path.exists(legacy_emb) and not os.path.exists(os.path.join(hiro_dir, 'embeddings.index')):
        shutil.copy2(legacy_emb, os.path.join(hiro_dir, 'embeddings.index'))
    if os.path.exists(legacy_meta) and not os.path.exists(os.path.join(hiro_dir, 'embeddings_metadata.msgpack')):
        shutil.copy2(legacy_meta, os.path.join(hiro_dir, 'embeddings_metadata.msgpack'))
    if os.path.exists('Hiro.json') and not os.path.exists(os.path.join(hiro_dir, 'personaje.json')):
        shutil.copy2('Hiro.json', os.path.join(hiro_dir, 'personaje.json'))
    if os.path.exists('./static/Hiro.jpg') and not os.path.exists(os.path.join(hiro_dir, 'avatar.jpg')):
        shutil.copy2('./static/Hiro.jpg', os.path.join(hiro_dir, 'avatar.jpg'))


def backup_datos():
    """Copia toda la carpeta data/ a backups/ con fecha. Corre una vez por día."""
    if os.path.exists('./data'):
        fecha = datetime.now().strftime('%Y%m%d')
        dest  = f'./backups/backup_{fecha}'
        if not os.path.exists(dest):
            shutil.copytree('./data', dest)
            print(f"✅ Backup creado: {dest}")


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN (funciona con __main__ Y con Gunicorn/wsgi)
# ─────────────────────────────────────────────────────────────────────────────

def _init_app():
    os.makedirs('./data', exist_ok=True)
    os.makedirs(PERSONAJES_DIR, exist_ok=True)
    migrar_hiro_default()
    backup_datos()
    cargar_personaje(get_personaje_activo_id())
    print("✅ Sistema listo")


_init_app()


if __name__ == '__main__':
    print("🚀 Iniciando Hiro Chat V4 - MULTIPERSONAJE...")
    print("\n💬 Abrí http://localhost:5000\n")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
