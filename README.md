🤖 Hiro Chat
Compañero virtual de roleplay con memoria persistente, multimodelo y multipersonaje.
Hiro Chat es una aplicación web local construida con Flask que te permite chatear con personajes de IA que realmente te recuerdan. No es solo un chatbot — tiene un sistema de memoria episódica, extracción de hechos, síntesis de conocimiento, embeddings semánticos con FAISS, evolución de relación a lo largo del tiempo, expresiones faciales, escenarios, eventos, diarios automáticos y soporte para múltiples proveedores de IA (Mistral, OpenRouter, OpenAI, Cohere, Jina, Ollama).
✨ Features principales

🧠 Memoria real — aprende sobre vos, genera síntesis, recuerda entre sesiones
👥 Multipersonaje — cada personaje tiene su propia DB, embeddings y config de API
🌐 Multimodelo — cambiá de proveedor o modelo sin tocar código
🎭 Sistema de expresiones — imágenes que cambian según la respuesta del personaje
📖 Diarios automáticos — el personaje escribe sobre lo que vivieron juntos
🌱 Evolución de fases — la relación y la personalidad cambian con el tiempo
⚡ Eventos y escenarios — narrativa dinámica con disparadores automáticos

🛠️ Cómo nació este proyecto
Este proyecto fue una colaboración humano-IA bastante inusual. La arquitectura, la lógica del backend, el sistema de memoria y la mayor parte del código fueron desarrollados en conversación con Claude (Anthropic) y Gemini (Google) — que actuaron como programadores principales. Gemini aportó mucho en la interfaz visual de las páginas; Claude en la programación, la arquitectura y la lógica del sistema de memoria. El humano detrás del proyecto aportó la visión, las ideas, las decisiones de diseño y todo lo que ninguna IA podía hacer sola.
Una demostración práctica de cómo se puede construir algo complejo colaborando con modelos de lenguaje desde cero.

📋 Licencia
Uso personal y no comercial. Ver LICENSE para más detalle.

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
