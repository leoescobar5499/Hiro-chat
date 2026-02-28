# Carpeta `data/`

Esta carpeta contiene los datos de configuración y personajes. **No se sube al repo** (ver `.gitignore`), excepto los archivos de ejemplo y el personaje por defecto.

## Primeros pasos

Antes de iniciar la app por primera vez, copiá los archivos `.example` a sus nombres reales:

```bash
cp data/api_config.example.json data/api_config.json
cp data/libreria_modelos.example.json data/libreria_modelos.json
cp data/modelos_activos.example.json data/modelos_activos.json
cp data/personaje_activo.example.json data/personaje_activo.json
```

Luego abrí la app en **http://localhost:5000** y configurá tus API keys desde el **⚙️ Gestor de APIs**.

## Estructura

```
data/
├── api_config.json          ← Tu configuración de APIs (keys, modelos). NO se sube.
├── libreria_modelos.json    ← Biblioteca de modelos que agregaste. NO se sube.
├── modelos_activos.json     ← Modelo activo por proveedor. NO se sube.
├── personaje_activo.json    ← Qué personaje está activo ahora. NO se sube.
│
└── personajes/
    └── hiro/                ← Personaje por defecto incluido en el repo
        ├── personaje.json   ← Ficha del personaje (se sube — es el demo)
        ├── expresiones.json ← Expresiones faciales del personaje (se sube)
        ├── memoria.db       ← Base de datos de memoria. NO se sube.
        ├── embeddings.index ← Índice vectorial FAISS. NO se sube.
        └── avatar.*         ← Imagen del personaje. NO se sube.
```

## Proveedores de API compatibles

| Proveedor | Uso | Link |
|-----------|-----|------|
| **Mistral** | Chat + embeddings (recomendado para empezar) | [console.mistral.ai](https://console.mistral.ai/api-keys/) |
| **OpenRouter** | Chat con cientos de modelos, muchos gratuitos | [openrouter.ai/keys](https://openrouter.ai/keys) |
| OpenAI | Chat + embeddings | [platform.openai.com](https://platform.openai.com/api-keys) |
| Cohere | Embeddings en español | [dashboard.cohere.com](https://dashboard.cohere.com/api-keys) |
| Ollama | Modelos locales sin API key | [ollama.ai](https://ollama.ai) |
