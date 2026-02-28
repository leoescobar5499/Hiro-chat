# Arquitectura del proyecto — Hiro Chat V4

## Mapa general

```
app.py                  ← arranque
├── memoria/            ← cerebro (paquete modular)
│   ├── __init__.py     ← re-exporta todo (compatibilidad total con el resto)
│   ├── faiss_store.py  ← índice vectorial FAISS + embeddings multi-proveedor
│   ├── extraccion.py   ← extracción de hechos con IA + memoria permanente
│   ├── enriquecimiento.py ← análisis episódico (resumen, temas, importancia)
│   ├── sintesis.py     ← síntesis de conocimiento + perfil narrativo
│   ├── emocional.py    ← sistema emocional + diarios + evolución + conciencia temporal
│   ├── relacion.py     ← fase de relación y métricas de progresión
│   ├── contexto.py     ← construcción de contexto y system prompt
│   └── _helpers.py     ← utilidades internas (solo uso dentro del paquete)
├── chat_engine.py      ← motor (procesa mensajes, sin cambios de interfaz)
├── routes.py           ← API HTTP (todos los endpoints)
├── utils.py            ← helpers compartidos (DB, LLM, paths)
├── modelos_utils.py    ← gestión de librería de modelos
└── crear_personaje.py  ← blueprint independiente de creación
```

Cada archivo tiene **una sola razón para cambiar**. La tabla de cada sección te dice exactamente dónde ir.

---

## `utils.py` — Base compartida

### Qué hace
La capa más baja. No importa nada del proyecto propio, solo librerías externas. Todo lo demás se apoya en él.

Contiene:
- **Zona horaria** (`now_argentina()`, `ARGENTINA_TZ`) — Argentina (UTC-3)
- **Cliente LLM** (`llamada_mistral_segura()`) — único punto de llamada a modelos de lenguaje. Soporta **Mistral** y **OpenRouter**. Lee todo desde `api_config.json`. Reintentos automáticos + fallback al proveedor secundario.
- **Cliente Mistral** (`mistral_client`, `_get_mistral_client()`) — inicialización lazy desde `api_config.json`. Usado exclusivamente para embeddings. Puede ser `None`; en ese caso FAISS queda desactivado pero el chat sigue funcionando.
- **Helper de embeddings** (`embeddings_disponibles()`) — devuelve True/False para degradar graciosamente sin Mistral.
- **Gestor de APIs** (`cargar_config_apis()`, `guardar_config_apis()`, `obtener_config_predeterminada()`) — lee y escribe `api_config.json` del personaje activo.
- **Resolución de modelo/proveedor** (`obtener_proveedor_actual()`, `_resolver_modelo_para_llamada()`) — enruta llamadas según proveedor primario/fallback configurado.
- **Detección NSFW** (`detectar_nsfw()`) — opcional; si está activada en config, puede disparar switch automático a OpenRouter.
- **Gestión de paths** (`paths()`, `PERSONAJES_DIR`, `ACTIVO_PATH`) — todas las rutas de archivos de un personaje en un solo dict.
- **Personaje activo** (`get_personaje_activo_id()`, `set_personaje_activo_id()`)
- **Base de datos** (`_get_conn()`) — conexión SQLite con encoding UTF-8 forzado.
- **Inicialización de DB** (`init_database_personaje()`) — crea todas las tablas y corre migraciones automáticas.
- **Importar/listar personajes** (`importar_personaje_desde_json()`, `listar_personajes()`)
- **Reparación de encoding** (`_reparar_encoding()`, `reparar_valor_db()`) — fix automático de latin-1/utf-8 corrupto.

### Cuándo modificarlo
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar zona horaria | `ARGENTINA_TZ` y `now_argentina()` |
| Cambiar el proveedor LLM activo | Gestor de APIs en la UI, o `api_config.json` directamente |
| Agregar un tercer proveedor LLM (ej: Gemini) | Nueva función `_llamar_gemini()` + enrutar en `llamada_mistral_segura()` |
| Cambiar modelo de embeddings | `obtener_embedding()` en `memoria/faiss_store.py` |
| Agregar una tabla nueva a la DB | `init_database_personaje()` |
| Cambiar la estructura de carpetas de personajes | `paths()` |
| El SDK de Mistral cambia de versión | `_llamar_mistral()` |

---

## `memoria/` — Motor de memoria (paquete modular)

El archivo `memoria.py` fue dividido en un paquete de 9 módulos. **El resto del proyecto (chat_engine, routes, app) no necesitó cambiar ninguna línea de importación** — el `__init__.py` re-exporta todo con la misma interfaz.

### `memoria/__init__.py` — Punto de entrada
Re-exporta todas las funciones públicas de los submódulos. Es el único archivo que importan `chat_engine.py` y `routes.py`. Si agregás una función nueva a cualquier submódulo y la querés exponer al exterior, la agregás acá.

Actualmente re-exporta también:
- `generar_diario_automatico` ← de `emocional.py`
- `actualizar_evolucion_automatica` ← de `emocional.py`

---

### `memoria/faiss_store.py` — Índice vectorial y embeddings
Todo lo relacionado con vectorización y búsqueda semántica.

Contiene:
- `faiss_index`, `embeddings_metadata` — estado global del índice activo
- `init_faiss_personaje()` — carga el índice del personaje o crea uno nuevo
- `guardar_faiss()` — persiste el índice a disco (usa pid explícito para evitar guardar en el personaje equivocado)
- `get_faiss_ntotal()` — acceso seguro al total de vectores
- `limpiar_faiss_episodios()` — elimina vectores de tipo episodio al limpiar historial
- `cargar_personaje()` — orquesta carga completa: DB + FAISS + escenario default
- `_asegurar_escenario_default()` — crea escenario desde el JSON si la DB está vacía
- `_detectar_proveedor_embedding()` — auto-detección del proveedor por nombre de modelo
- `_embedding_mistral/openai/cohere/jina/ollama()` — sub-funciones por proveedor
- `obtener_embedding()` — punto único de generación de embeddings, con fallback a Mistral
- `agregar_embedding()` — agrega vector al índice y persiste
- `buscar_contexto_relevante()` — búsqueda semántica por similitud coseno

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Agregar un proveedor de embeddings nuevo | Nueva función `_embedding_<proveedor>()` + caso en `obtener_embedding()` |
| Cambiar la dimensión del índice FAISS (ej: a 768) | `faiss.IndexFlatL2(1024)` → nueva dimensión (requiere limpiar índice existente) |
| Cambiar el modelo de embeddings de Mistral | `model="mistral-embed"` en `_embedding_mistral()` |

---

### `memoria/extraccion.py` — Extracción de hechos con IA
Qué aprende el personaje sobre el usuario y cómo.

Contiene:
- `_get_modo_memoria()` — lee `modo_memoria` del JSON (`roleplay` o `compañero`)
- `extraer_informacion_con_ia()` — prompt especializado por modo; devuelve lista de hechos estructurados. Modo **compañero** tiene categorías ampliadas:
  - `identidad`, `apariencia`, `vida`, `trabajo_estudio`, `familia`, `rutina`, `salud`, `relaciones`, `personalidad`, `intereses`, `objetivos`, `sueños`, `estado_actual`
  - Modo **roleplay**: categorías más básicas sin las de vida cotidiana
- `guardar_memoria_permanente()` — upsert en SQLite + embedding por cada hecho. Descarta `estado_actual` (efímero).
- `extraer_menciones_casuales()` — captura temas mencionados de pasada; los guarda como hilos pendientes
- `_detectar_y_cerrar_hilos()` — marca como resueltos los hilos cuando el usuario los retoma
- `MAPA_CATS` — diccionario de normalización de categorías mal escritas por el LLM

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Agregar una categoría de memoria nueva | Prompt de `extraer_informacion_con_ia()` + `MAPA_CATS` si hace falta alias |
| Cambiar qué categorías se guardan vs se descartan | `guardar_memoria_permanente()` (filtro de `estado_actual`) |
| Agregar un modo de memoria nuevo (ej: `narrador`) | `_get_modo_memoria()` + nuevo bloque en `extraer_informacion_con_ia()` |
| Ajustar el umbral de confianza mínima | `if confianza < 70: continue` en `extraer_informacion_con_ia()` |
| Cambiar cuántas menciones casuales se guardan por turno | `menciones[:3]` en `extraer_menciones_casuales()` |

---

### `memoria/enriquecimiento.py` — Análisis episódico
Rellena los campos analíticos de cada episodio guardado.

Contiene:
- `_enriquecer_episodio()` — después de guardar un episodio, llama a IA para:
  - `resumen`: una oración de qué pasó
  - `temas`: lista de temas del intercambio
  - `emocion_detectada`: emoción principal del usuario
  - `importancia`: 1-10 según escala estricta predefinida
  - También actualiza `temas_frecuentes` en la tabla `relacion` (top 8 de los últimos 30 episodios)

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar la escala de importancia | Sección "ESCALA DE IMPORTANCIA" en el prompt |
| Agregar un campo nuevo al análisis episódico | Prompt + UPDATE en la DB (requiere migración en `utils.py`) |
| Cambiar cuántos episodios se usan para temas frecuentes | `LIMIT 30` en el SELECT |

---

### `memoria/sintesis.py` — Síntesis de conocimiento
Genera las narrativas de largo plazo sobre el usuario y la relación.

Contiene:
- `_debe_regenerar_sintesis()` — triggers: A) 3+hs de pausa, B) 15+ hechos nuevos, C) 72+hs fallback
- `_ejecutar_sintesis()` — pipeline: perfil → relación → categorías
- `generar_perfil_narrativo()` — párrafo en prosa sobre quién es el usuario (máx 50 palabras, anti-alucinación)
- `generar_resumen_relacion()` — párrafo sobre la historia entre los dos, basado en momentos con fechas reales
- `generar_sintesis()` — síntesis por categoría para las que tienen 3+ hechos

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar cuándo se regenera la síntesis | `_debe_regenerar_sintesis()` (umbrales de horas y hechos) |
| Cambiar el estilo del perfil narrativo | Prompt en `generar_perfil_narrativo()` |
| Cambiar el mínimo de hechos para sintetizar una categoría | `if len(hechos) < 3: continue` en `generar_sintesis()` |

---

### `memoria/emocional.py` — Sistema emocional, diarios y evolución
Todo lo relacionado con el estado emocional del usuario, la noción del tiempo del personaje, los diarios automáticos y la evolución del personaje por fase.

#### Helpers de conciencia temporal (usados por `contexto.py` en el system prompt):
- `_get_gap_sesion()` — calcula horas desde la última sesión; devuelve `(horas, texto_para_personaje, es_primera_hoy)`. Cubre desde "mismo hilo" hasta "más de un mes ausente".
- `_get_tendencia_emocional()` — analiza últimas 10 emociones detectadas; alerta si hay tristeza recurrente (≥3 registros, intensidad ≥3) o alegría sostenida (≥5 registros).
- `_get_resumen_ultima_sesion()` — recupera resúmenes de episodios importantes (importancia ≥ 5) para dar hilo narrativo entre sesiones.
- `_get_horario_habitual()` — detecta la franja horaria habitual del usuario (>60% de mensajes en los últimos 40); alerta si la sesión actual es inusual.

#### Sistema emocional:
- `detectar_emocion()` — llama a IA para clasificar la emoción del mensaje del usuario (7 emociones: alegria/tristeza/miedo/enojo/neutral/confusion/sorpresa, intensidad 1-5); guarda en `estado_emocional`.
- `generar_backstory_automatico()` — cada 50 mensajes del usuario, genera una entrada de diario privado del personaje usando todos los hechos aprendidos, momentos y tendencia emocional. Guarda en `backstory_aprendido` (registro único, se reemplaza).

#### Diarios automáticos (nuevo):
- `generar_diario_automatico()` — genera una entrada de diario del personaje en la tabla `diarios_personaje`. Incluye nombre del personaje, estado de relación (fase, confianza), hechos aprendidos, momentos compartidos y tendencia emocional reciente. **Anti-duplicado**: verifica si ya existe un diario automático del día actual antes de generar.
  - Triggers desde `chat_engine._post_proceso`:
    - Gap ≥ 3 horas desde el penúltimo mensaje del usuario (nueva sesión)
    - Cada 25 mensajes del usuario

#### Evolución de fases (nuevo):
- `actualizar_evolucion_automatica(fase_actual)` — genera/actualiza en la tabla `evolucion_fases` una descripción de cómo es el personaje en la fase actual. Produce dos campos vía IA: `descripcion` (presencia emocional, actitud) y `personalidad` (gestos, forma de hablar, hábitos). Usa la descripción base del `personaje.json` como referencia.
  - Triggers desde `chat_engine._post_proceso`:
    - La fase sube (fase_actual > fase guardada en `evolucion_fases`)
    - Cada 40 mensajes del usuario

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar el umbral de "gap notable" | `if horas < 2` en `_get_gap_sesion()` |
| Cambiar las categorías de emoción detectadas | Prompt de `detectar_emocion()` |
| Cambiar cuándo el personaje nota el horario inusual | Lógica de `_get_horario_habitual()` + uso en `contexto.py` |
| Cambiar la frecuencia del backstory | `msg_count % 50 == 0` en `chat_engine.py` |
| Cambiar el estilo del backstory del personaje | Prompt en `generar_backstory_automatico()` |
| Cambiar el estilo de los diarios automáticos | Prompt en `generar_diario_automatico()` |
| Cambiar la frecuencia del diario automático | Triggers en `_post_proceso` de `chat_engine.py` (`horas_gap >= 3` y `msg_count % 25`) |
| Cambiar la frecuencia de actualización de evolución | `msg_count % 40 == 0` en `chat_engine.py` |
| Cambiar qué campos genera la evolución de fase | Prompt en `actualizar_evolucion_automatica()` |

---

### `memoria/relacion.py` — Fase de relación
Métricas de progresión de la relación entre usuario y personaje.

Contiene:
- `actualizar_fase()` — recalcula después de cada mensaje:
  - `nivel_confianza` = mensajes × 2 + momentos × 5 (cap 100)
  - `nivel_intimidad` = momentos × 8 + hechos_íntimos × 10 (cap 100)
  - `dias_juntos` = días desde primer mensaje
  - `fase` 1-4 según umbrales de mensajes e intimidad
  - **Frenos por sesión** (`TOPES_CONFIANZA`, `TOPES_INTIMIDAD`): evitan que la relación llegue al máximo el primer día

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Acelerar o frenar la progresión | Multiplicadores en las fórmulas de `nivel_confianza` e `nivel_intimidad` |
| Cambiar los topes por día | Diccionarios `TOPES_CONFIANZA` y `TOPES_INTIMIDAD` |
| Cambiar cuántos mensajes hacen falta para cada fase | Condicionales `if total_msgs < 20` etc. |

---

### `memoria/contexto.py` — Contexto y system prompt
Construye lo que el personaje "ve" en cada respuesta.

Contiene:
- `obtener_contexto()` — arma el bloque de memoria en 5 bloques:
  1. Hilo de la última sesión (si hay gap ≥ 3hs)
  2. Quién es el usuario (perfil narrativo de síntesis)
  3. Datos de referencia (hechos permanentes por categoría)
  4. Historia entre ustedes (timeline de momentos + resumen relacional)
  5. Contexto semántico relevante (búsqueda FAISS por similitud al mensaje actual)
  - Modo liviano (saludos, despedidas, mensajes funcionales): omite FAISS y sesión
- `obtener_system_prompt()` — construye el prompt completo con:
  - Descripción y personalidad del personaje (desde `personaje.json`)
  - Escenario activo, fecha/hora argentina, fase actual
  - **Conciencia de sesión**: gap de tiempo + instrucción específica según duración
  - **Tendencia emocional**: si hay patrón recurrente de tristeza/alegría
  - **Horario inusual**: si la conexión es fuera de la franja habitual
  - Eventos disparados y objetos activos
  - Hechos confirmados (ancla anti-alucinación)
  - Reglas de contacto físico según fase (slow burn real)
  - Gestos recientes (evita repetición)
  - Calibración de tono (funcional vs emocional vs casual)
  - Hilos pendientes y promesas pendientes
  - Reglas de respuesta con ejemplos concretos de qué hacer y qué no

**Cuándo modificarlo:**
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar cómo responde el personaje | Sección "REGLAS DE RESPUESTA" en `obtener_system_prompt()` |
| Cambiar qué memoria se pasa como contexto | `obtener_contexto()` — agregar/quitar bloques |
| Cambiar el límite de contacto físico por fase | Diccionario `contacto_por_fase` |
| Cambiar cómo detecta mensajes funcionales vs casuales | Listas de palabras clave en la sección de calibración de tono |
| Cambiar cuántos hechos confirmados ve el personaje | `hechos_confirmados[:15]` |
| Agregar un bloque nuevo al contexto | Nueva función en `emocional.py` + llamarla en `obtener_contexto()` |

---

### `memoria/_helpers.py` — Utilidades internas
**Solo uso interno del paquete.** No importar desde fuera.

Contiene:
- `_limpiar_json()` — parsea respuestas de LLM que pueden venir con markdown, texto extra o JSON malformado. Intenta múltiples estrategias de extracción con matching de brackets balanceado.

---

## `chat_engine.py` — Motor del chat

### Qué hace
Orquesta el flujo de una conversación. No sabe nada de HTTP, no toca templates. Recibe un mensaje, procesa, llama al LLM, guarda todo y devuelve la respuesta.

Contiene:
- `_recortar_respuesta()` — corta la respuesta en la oración que no pase las 120 palabras (configurable).
- `_get_escenario_id_actual()` — devuelve el id del escenario activo para guardarlo en el episodio.
- `_procesar_mensaje()` — flujo completo:
  1. Guarda mensaje del usuario en DB
  2. Actualiza `ultimo_mensaje` en `relacion`
  3. Obtiene historial (últimos 10 mensajes)
  4. Construye contexto + system prompt
  5. Llama al LLM (mistral-large-latest, temp 0.88, max 600 tokens)
  6. Recorta y guarda respuesta
  7. Lanza `_post_proceso` en **thread background** (el usuario ya tiene su respuesta)

  **`_post_proceso` (background):**
  - Cierra hilos pendientes relevantes
  - Extrae hechos con IA y los guarda en memoria permanente
  - Extrae menciones casuales → hilos
  - Genera embedding + guarda episodio (con deduplicación por ventana de 60 segundos)
  - Enriquece el episodio (resumen, emoción, importancia)
  - Detecta emoción del mensaje
  - **Backstory** cada 50 mensajes
  - **Diario automático**: si gap ≥ 3hs O cada 25 mensajes
  - **Evolución de fase**: si la fase subió O cada 40 mensajes
  - Verifica y dispara síntesis si corresponde

- `_procesar_continuar()` — igual pero sin mensaje del usuario: el personaje continúa la escena; filtra categorías (`apariencia`, `estado_actual`, `momentos`) para no contaminar la memoria con datos inventados.
- `verificar_eventos_automaticos()` — revisa eventos pendientes con soporte completo de:
  - **tipo `mensajes`**: dispara cuando el historial alcanza N mensajes
  - **tipo `fecha`**: soporte para `DD-MM` (anual recurrente) y `DD-MM-AAAA` (única vez), con `hora` opcional en formato `HH:MM`
  - **`aviso_dias`**: avisa N días antes del evento
  - **`seguimiento`**: dispara un mensaje de seguimiento después de que pasó el evento
  - **tipo `manual`**: ignorado (se dispara solo desde la UI)

### Cuándo modificarlo
| Situación | Qué tocar |
|-----------|-----------|
| Cambiar el modelo de chat | `model=` en `llamada_mistral_segura()` dentro de `_procesar_mensaje()` y `_procesar_continuar()` |
| Cambiar el límite de palabras por respuesta | `limite=120` en `_recortar_respuesta()` + regla en `contexto.py` |
| Cambiar cuántos mensajes de historial se envían al LLM | `LIMIT 10` en el SELECT de `_procesar_mensaje()` |
| Cambiar la instrucción de "continuar" | String `instruccion` en `_procesar_continuar()` |
| Cambiar qué categorías se filtran en modo continuar | `categorias_excluidas` en `_procesar_continuar()` |
| Cambiar la frecuencia del backstory | `msg_count % 50 == 0` |
| Cambiar la frecuencia del diario automático | `horas_gap >= 3` y `msg_count % 25` |
| Cambiar la frecuencia de la evolución automática | `msg_count % 40 == 0` |
| Agregar streaming de respuesta | Refactorizar `_procesar_mensaje()` para modo stream del SDK |
| Agregar un nuevo tipo de evento automático (ej: por hora) | `verificar_eventos_automaticos()` |

---

## `routes.py` — API HTTP

### Qué hace
Define todos los endpoints Flask como un Blueprint (`bp`). No contiene lógica de negocio: recibe el request, llama a la función correcta, devuelve JSON.

### Bloques de endpoints

#### Gestor de APIs
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/config/apis` | Leer `api_config.json` |
| POST | `/api/config/apis` | Guardar config de APIs |
| POST | `/api/config/test-apis` | Testear conexión con proveedor |

#### Modelos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/models/mistral` | Listar modelos Mistral disponibles |
| GET | `/api/models/openrouter` | Listar modelos OpenRouter disponibles |
| GET | `/api/models/activos` | Modelo de chat activo |
| POST | `/api/models/cambiar` | Cambiar modelo de chat |
| POST | `/api/models/probar` | Probar un modelo con un mensaje |
| POST | `/api/models/search` | Buscar modelos |
| GET | `/api/models/validate/<modelo_id>` | Validar que un modelo existe |
| GET | `/api/models/info/<modelo_id>` | Info de un modelo |
| GET | `/api/models/all-for-tasks` | Todos los modelos ordenados por tarea |

#### Personajes
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/personajes` | Listar personajes |
| GET | `/api/personajes/activo` | Personaje activo actual |
| POST | `/api/personajes/cambiar` | Cambiar personaje activo |
| POST | `/api/personajes/importar` | Importar personaje desde JSON + imagen |
| GET | `/api/personajes/<pid>/avatar` | Servir avatar |
| GET | `/api/personajes/activo/ficha` | Leer ficha del personaje activo |
| PUT | `/api/personajes/activo/ficha` | Editar ficha del personaje activo |
| POST | `/api/personajes/activo/avatar` | Subir nuevo avatar |
| DELETE | `/api/personajes/<pid>` | Eliminar personaje |

#### Páginas HTML
| Ruta | Template |
|------|---------|
| `/` | `index.html` |
| `/sobre_vos` | `sobre_vos.html` |
| `/editar_personaje` | `editar_personaje.html` |
| `/escenarios` | `escenarios.html` |
| `/eventos` | `eventos.html` |
| `/objetos` | `objetos.html` |
| `/expresiones` | `expresiones.html` |
| `/api_manager` | `api_manager.html` |

#### Chat
| Método | Ruta | Función |
|--------|------|---------|
| POST | `/api/chat` | Enviar mensaje (principal) |
| POST | `/api/continuar` | Personaje continúa sin input |
| POST | `/api/mensaje` | Alias legacy de `/api/chat` |
| POST | `/api/cancelar_ultimo` | Cancelar/borrar el último intercambio |

#### Stats, historial y perfil
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/stats` | Estadísticas generales |
| GET | `/api/perfil` | Perfil completo de memoria |
| GET | `/api/historial` | Historial completo de chat |
| DELETE | `/api/historial` | Limpiar historial |

#### CRUD mensajes
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/mensaje/<msg_id>` | Obtener mensaje |
| PUT | `/api/mensaje/<msg_id>` | Editar mensaje |
| DELETE | `/api/mensaje/<msg_id>` | Eliminar mensaje |

#### CRUD memoria
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/memoria/hecho/<hid>` | Obtener hecho |
| PUT | `/api/memoria/hecho/<hid>` | Editar hecho |
| DELETE | `/api/memoria/hecho/<hid>` | Eliminar hecho |
| DELETE | `/api/memoria/categoria/<cat>` | Borrar categoría entera |
| DELETE | `/api/memoria/limpiar-todo` | Borrar toda la memoria |
| DELETE | `/api/reset-total` | Reset total (borra todo + reinicia DB) |

#### CRUD síntesis
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/sintesis` | Listar síntesis |
| GET | `/api/sintesis/<sid>` | Obtener síntesis |
| (más endpoints de síntesis) | | |

#### CRUD diarios (nuevo)
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/diarios` | Listar entradas de diario (id, titulo, contenido, fecha, auto) |
| POST | `/api/diarios` | Crear entrada manual |
| PUT | `/api/diarios/<did>` | Editar entrada (contenido y/o título) |
| DELETE | `/api/diarios/<did>` | Eliminar entrada |

#### CRUD evolución de fases (nuevo)
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/evolucion` | Listar evolución por fase (descripcion, personalidad, fecha) |
| PUT | `/api/evolucion/<fase>` | Crear/actualizar evolución de una fase (upsert) |
| DELETE | `/api/evolucion/<fase>` | Eliminar evolución de una fase |
| POST | `/api/evolucion/generar` | Generar evolución de una fase con IA |

#### CRUD expresiones (nuevo)
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/expresiones` | Listar expresiones |
| POST | `/api/expresiones` | Crear expresión |
| PUT | `/api/expresiones/<eid>` | Editar expresión |
| DELETE | `/api/expresiones/<eid>` | Eliminar expresión |
| POST | `/api/expresiones/<eid>/default` | Marcar como expresión por defecto |
| GET | `/api/expresiones/<eid>/imagen` | Servir imagen de expresión |

#### CRUD escenarios, eventos, objetos
| Método | Ruta | Función |
|--------|------|---------|
| (endpoints CRUD completos) | `/api/escenarios/...` | Escenarios |
| (endpoints CRUD completos) | `/api/eventos/...` | Eventos |
| (endpoints CRUD completos) | `/api/objetos/...` | Objetos |

#### Librería de modelos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/libreria/modelos` | Listar librería personal |
| POST | `/api/libreria/agregar` | Agregar modelo a librería |
| GET/DELETE | `/api/libreria/modelo/<modelo_id>` | Ver/eliminar de librería |
| GET | `/api/libreria/asignaciones` | Ver asignaciones por tarea |
| POST | `/api/libreria/asignar` | Asignar modelo a tarea |
| GET | `/api/libreria/tarea/<tarea>` | Modelo asignado a una tarea |
| GET | `/api/libreria/buscar` | Buscar en librería |
| GET | `/api/libreria/tag/<tag>` | Modelos por tag |
| GET | `/api/libreria/tareas` | Tareas disponibles |

#### Export / Import
Soporte completo para exportar e importar todas las tablas como JSON.

| Tabla | Exportar | Importar |
|-------|---------|---------|
| Completo (todas) | GET `/api/exportar/completo` | POST `/api/importar/completo` |
| Chat | (via historial) | POST `/api/importar/chat` |
| Memoria | (via perfil) | POST `/api/importar/memoria` |
| Episódica | GET `/api/exportar/episodica` | POST `/api/importar/episodica` |
| Relación | GET `/api/exportar/relacion` | POST `/api/importar/relacion` |
| Escenarios | GET `/api/exportar/escenarios` | POST `/api/importar/escenarios` |
| Eventos | GET `/api/exportar/eventos` | POST `/api/importar/eventos` |
| Objetos | GET `/api/exportar/objetos` | POST `/api/importar/objetos` |
| Diarios | GET `/api/exportar/diarios` | POST `/api/importar/diarios` |
| Evolución | GET `/api/exportar/evolucion` | POST `/api/importar/evolucion` |

### Cuándo modificarlo
| Situación | Qué tocar |
|-----------|-----------|
| Agregar un endpoint nuevo | `@bp.route(...)` en el bloque correspondiente |
| Cambiar la URL de un endpoint | El decorador `@bp.route(...)` |
| Agregar validación a un endpoint | Dentro del handler, antes de llamar a la lógica |
| Cambiar el prompt de generación IA de escenarios/eventos/objetos/evolución | Prompts inline dentro de los handlers `api_generar_*` y `generar_evolucion_ia` |

---

## `utils.py` / `modelos_utils.py` — Gestión de modelos

`modelos_utils.py` maneja la librería personal de modelos y las asignaciones por tarea:
- `cargar_modelos_activos()`, `cambiar_modelo()` — modelo activo para chat
- `listar_modelos_mistral()`, `listar_modelos_openrouter()` — catálogos disponibles
- `agregar_modelo_a_libreria()`, `listar_modelos_libreria()`, `eliminar_modelo_libreria()` — librería personal
- `asignar_modelo_a_tarea()`, `obtener_asignaciones()`, `obtener_modelo_para_tarea()` — asignaciones
- `TAREAS_DISPONIBLES` — lista de tareas válidas: `chat`, `embeddings`, `extraction`, `synthesis`, `generation`, `enrichment`

**Modelos configurados actualmente:**
| Tarea | Modelo | Proveedor |
|-------|--------|-----------|
| chat | configurable (Mistral Large o OpenRouter) | Mistral / OpenRouter |
| embeddings | `mistral-embed` | Mistral |
| extraction | `mistral-small-latest` | Mistral |
| synthesis | `mistral-small-latest` | Mistral |
| generation | `mistral-small-latest` | Mistral |
| enrichment | `mistral-small-latest` | Mistral |

---

## `app.py` — Arranque

### Qué hace
Punto de entrada. Inicializa, configura y conecta las piezas. No contiene lógica de negocio.

Contiene:
- Creación de `app = Flask(__name__)`
- Registro de blueprints (`routes.bp` y `crear_personaje.crear_bp`)
- `migrar_hiro_default()` — migración one-shot de estructura legacy a carpeta de personajes
- `backup_datos()` — copia `./data/` a `./backups/backup_YYYYMMDD/` una vez por día
- `_init_app()` — secuencia de arranque: crear carpetas → migrar → backup → cargar personaje activo

### Cuándo modificarlo
| Situación | Qué tocar |
|-----------|-----------|
| Agregar un blueprint nuevo | Importar y registrar con `app.register_blueprint()` |
| Cambiar el puerto o modo debug | Línea `app.run(...)` al final |
| Cambiar la frecuencia o destino del backup | `backup_datos()` |
| Agregar middleware global (CORS, auth, logging) | Antes del registro de blueprints |

---

## `crear_personaje.py` — Blueprint de creación

Blueprint independiente bajo `/crear`. Usa Mistral para generar fichas en tres modos: Express, Preguntas y Paso a paso. Sin cambios desde la refactorización.

---

## Estructura de datos en disco

```
data/
├── personaje_activo.json       ← id del personaje activo
├── modelos_activos.json        ← modelo de chat seleccionado
├── libreria_modelos.json       ← librería personal de modelos
└── personajes/
    └── <pid>/                  ← ej: hiro, roronoa_zoro_cc4071
        ├── personaje.json      ← ficha del personaje (chara_card_v2)
        ├── memoria.db          ← SQLite con toda la memoria
        ├── api_config.json     ← configuración de APIs de este personaje
        ├── embeddings.index    ← índice FAISS
        ├── embeddings_metadata.msgpack  ← metadata de cada vector
        ├── avatar.jpg          ← imagen del personaje
        └── expresiones/        ← carpeta de imágenes de expresiones
            └── expresiones.json ← metadata de expresiones (nombre, archivo, default)
```

### Tablas SQLite por personaje (`memoria.db`)
| Tabla | Qué guarda |
|-------|-----------|
| `mensajes` | Historial completo de chat (rol, contenido, timestamp) |
| `memoria_permanente` | Hechos sobre el usuario (categoria, clave, valor, confianza) |
| `memoria_episodica` | Episodios enriquecidos (resumen, temas, emoción, importancia) |
| `sintesis_conocimiento` | Perfil narrativo, resumen relacional, síntesis por categoría |
| `relacion` | Fase, confianza, intimidad, días juntos, temas frecuentes |
| `escenarios` | Escenarios disponibles (nombre, descripción, historia, color, tono) |
| `eventos` | Eventos con ciclo de vida completo (disparado, consumido, duración, aviso_dias, seguimiento, hora) |
| `objetos` | Objetos en escena (propiedades, estado, poseedor, keyword) |
| `objetos_cambios_pendientes` | Sugerencias de cambio de objeto pendientes de confirmación |
| `hilos_pendientes` | Temas mencionados de pasada, pendientes de retomar |
| `estado_emocional` | Historial de emociones detectadas (emoción, intensidad, fecha) |
| `backstory_aprendido` | Diario del personaje (una entrada, se reemplaza cada 50 msgs) |
| `diarios_personaje` | Entradas de diario del personaje (titulo, contenido, fecha, auto) — múltiples entradas, `auto=1` indica generación automática |
| `evolucion_fases` | Descripción del personaje por fase (fase 1-4, descripcion, personalidad, fecha_actualizacion) — una fila por fase, upsert |

---

## Diagrama de dependencias

```
crear_personaje.py
    └── utils.py

app.py
    ├── utils.py
    ├── memoria/   (paquete)
    ├── routes.py
    └── crear_personaje.py

routes.py
    ├── utils.py
    ├── modelos_utils.py
    ├── memoria/   (cargar_personaje, limpiar_faiss_episodios, _ejecutar_sintesis,
    │              generar_perfil_narrativo, generar_resumen_relacion, generar_sintesis)
    └── chat_engine.py

chat_engine.py
    ├── utils.py
    └── memoria/   (obtener_contexto, obtener_system_prompt, actualizar_fase,
                    extraer_informacion_con_ia, guardar_memoria_permanente,
                    agregar_embedding, _enriquecer_episodio,
                    _debe_regenerar_sintesis, _ejecutar_sintesis,
                    get_faiss_ntotal, extraer_menciones_casuales,
                    _detectar_y_cerrar_hilos, detectar_emocion,
                    generar_backstory_automatico,
                    generar_diario_automatico,       ← nuevo
                    actualizar_evolucion_automatica) ← nuevo

memoria/  (paquete)
    ├── __init__.py         ← re-exporta todo
    ├── faiss_store.py      ← usa: utils
    ├── extraccion.py       ← usa: utils, _helpers, faiss_store
    ├── enriquecimiento.py  ← usa: utils, _helpers
    ├── sintesis.py         ← usa: utils
    ├── emocional.py        ← usa: utils, _helpers
    ├── relacion.py         ← usa: utils
    ├── contexto.py         ← usa: utils, faiss_store, emocional
    └── _helpers.py         ← usa: solo stdlib (re, json)

utils.py
    └── (solo librerías externas: mistralai, sqlite3, etc.)

modelos_utils.py
    └── (independiente, solo json/os)
```

**Regla de dependencias:** solo bajan. Ningún módulo importa a uno que esté más arriba en el grafo. Dentro del paquete `memoria/`, los módulos solo importan a `_helpers` y entre sí siguiendo el orden: `_helpers` → `faiss_store` → `extraccion`/`enriquecimiento`/`sintesis`/`emocional`/`relacion` → `contexto` → `__init__`.

---

## Flujo de un mensaje (referencia rápida)

```
Usuario escribe
    │
    ▼
routes.py /api/chat
    │
    ▼
chat_engine._procesar_mensaje()
    ├── Guarda mensaje en DB
    ├── Llama obtener_contexto() + obtener_system_prompt()
    ├── Llama LLM (mistral-large-latest)
    ├── Guarda respuesta
    ├── actualizar_fase()
    └── Thread background _post_proceso():
            ├── _detectar_y_cerrar_hilos()
            ├── extraer_informacion_con_ia() → guardar_memoria_permanente()
            ├── extraer_menciones_casuales()
            ├── agregar_embedding() → _enriquecer_episodio()
            ├── detectar_emocion()
            ├── [cada 50 msgs] generar_backstory_automatico()
            ├── [gap≥3hs o cada 25 msgs] generar_diario_automatico()
            ├── [fase subió o cada 40 msgs] actualizar_evolucion_automatica()
            └── [si corresponde] _ejecutar_sintesis()
```
