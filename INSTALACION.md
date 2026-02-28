# Instalación — Linux

> Probado en Ubuntu 22.04 / Debian 12. Requiere Python 3.10 o superior.

---

## 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/hiro-chat.git
cd hiro-chat
```

## 2. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

## 3. Ejecutar el instalador

```bash
bash install.sh
```

Esto crea el entorno virtual e instala todo automáticamente.

## 4. Configurar las APIs

Antes de iniciar, necesitás al menos una API key para que el chat funcione.

- **Mistral** (recomendado para empezar — tiene tier gratuito): [console.mistral.ai](https://console.mistral.ai/api-keys/)
- **OpenRouter** (más modelos, incluyendo gratuitos): [openrouter.ai/keys](https://openrouter.ai/keys)

Las configurás desde la app en **⚙️ Gestor de APIs** una vez que la iniciés.

## 5. Iniciar la app

```bash
bash run_app.sh
```

Abrí tu navegador en **http://localhost:5000**

---

## Inicios siguientes

Solo necesitás correr:

```bash
bash run_app.sh
```

---

## Problemas comunes

**`python3: command not found`**
```bash
sudo apt install python3
```

**`pip: command not found`**
```bash
sudo apt install python3-pip
```

**La app abre pero no responde al chat**
→ Revisá que tengas una API key configurada en el Gestor de APIs.

**Puerto 5000 ocupado**
```bash
# Ver qué proceso lo usa
sudo lsof -i :5000
# O cambiar el puerto en app.py → app.run(port=5001)
```
