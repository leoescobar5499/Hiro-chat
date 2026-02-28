# Hiro Chat

**Compañero virtual con memoria real.** Una app web local que te permite chatear con personajes de IA que aprenden sobre vos, evolucionan con el tiempo y recuerdan todo entre sesiones.

> Construida con Flask, FAISS, SQLite y soporte para múltiples proveedores de IA.

---

## ¿Qué hace?

No es un chatbot genérico. Cada personaje tiene su propia base de datos, índice vectorial y configuración. La relación evoluciona a lo largo del tiempo: el personaje aprende quién sos, recuerda lo que hablaron, y cambia con el tiempo.

**Sistema de memoria**
- Extracción automática de hechos desde la conversación
- Memoria episódica con búsqueda semántica (FAISS + embeddings)
- Síntesis periódica del conocimiento acumulado
- Perfil narrativo del usuario que se actualiza solo

**Personajes y relación**
- Multipersonaje — cada uno con su propia DB, embeddings y config
- Evolución por fases — la dinámica cambia a medida que la relación crece
- Expresiones faciales que responden al contenido del mensaje
- Diarios automáticos escritos desde la perspectiva del personaje
- Escenarios y eventos con disparadores narrativos

**Técnico**
- Multimodelo y multiproveedores — Mistral, OpenRouter, OpenAI, Cohere, Jina, Ollama
- Cambiás de modelo o proveedor desde la UI sin tocar código
- Todo corre local — tus datos no salen de tu máquina

---

## Instalación

Requiere Python 3.10+ en Linux.

```bash
git clone https://github.com/leoescobar5499/hiro-chat.git
cd hiro-chat
bash install.sh
bash run_app.sh
```

Abrí **http://localhost:5000** y configurá tu API key desde **⚙️ Gestor de APIs**.

Necesitás al menos una API key para que el chat funcione. Las opciones gratuitas para empezar:
- [Mistral](https://console.mistral.ai/api-keys/) — recomendado, tiene tier gratuito
- [OpenRouter](https://openrouter.ai/keys) — cientos de modelos, muchos gratuitos

---

## Configuración de APIs

| Proveedor | Para qué | Link |
|-----------|----------|------|
| **Mistral** | Chat + embeddings | [console.mistral.ai](https://console.mistral.ai/api-keys/) |
| **OpenRouter** | Chat con muchos modelos | [openrouter.ai/keys](https://openrouter.ai/keys) |
| OpenAI | Chat + embeddings | [platform.openai.com](https://platform.openai.com/api-keys) |
| Cohere | Embeddings en español | [dashboard.cohere.com](https://dashboard.cohere.com/api-keys) |
| Ollama | Modelos locales, sin key | [ollama.ai](https://ollama.ai) |

---

## Cómo nació este proyecto

Una colaboración bastante inusual entre un humano y dos IAs. La arquitectura, el backend y el sistema de memoria se desarrollaron en conversación con Claude (Anthropic) — que actuó como programador principal. Gemini (Google) aportó en la interfaz visual. El humano detrás del proyecto aportó la visión, las decisiones de diseño y todo lo que ninguna IA podía hacer sola.

Una demostración práctica de lo que se puede construir colaborando con modelos de lenguaje desde cero.

---

## Licencia

Uso personal y no comercial. Ver [LICENSE](LICENSE.md) para más detalle.
