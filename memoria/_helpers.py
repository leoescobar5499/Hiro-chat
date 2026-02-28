# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/_HELPERS.PY — Utilidades internas compartidas entre módulos
# No importar desde fuera del paquete. Solo uso interno.
# ═══════════════════════════════════════════════════════════════════════════

import re
import json


def _limpiar_json(texto, esperar_array=False):
    """
    Limpia la respuesta de un LLM y extrae el JSON puro.
    - Elimina bloques ```json ... ``` o ``` ... ```
    - Extrae el primer objeto {} o array [] encontrado con matching balanceado
    - Maneja strings escapados correctamente (cualquier nivel de anidamiento)
    - Devuelve None si no hay JSON parseable
    """
    if not texto:
        return None
    texto = texto.strip()
    # Quitar bloque markdown
    texto = re.sub(r'^```(?:json)?\s*', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\s*```$', '', texto)
    texto = texto.strip()
    if not texto:
        return None

    # Intento directo primero
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # Búsqueda con matching de brackets balanceados
    open_char  = '[' if esperar_array else '{'
    close_char = ']' if esperar_array else '}'

    start = texto.find(open_char)
    if start == -1:
        return None

    depth       = 0
    in_string   = False
    escape_next = False

    for i, ch in enumerate(texto[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                candidate = texto[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

    return None
