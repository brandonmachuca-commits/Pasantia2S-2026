"""Enrutamiento dinámico y síntesis de evidencia con Ollama."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Mapping

import requests


# Descripciones para las carpetas conocidas. No forman una lista permitida:
# las carpetas que existan realmente en Documentos se descubren al iniciar.
AGENTES = {
    "cursos": "programas, contenidos, asignaturas, previaturas y créditos",
    "materias": "materias, planes de estudio y datos de asignaturas",
    "parciales": "fechas, parciales, exámenes y evaluaciones",
    "horarios": "días, horarios, turnos, salones y presencialidad de clase",
    "docentes": "nombres de docentes y asignaturas que dictan",
    "perfil_ingreso": "requisitos y vías para ingresar a la carrera",
    "perfil_egreso": "competencias y capacidades al egresar",
    "info_general": "información institucional, puntajes y reglas generales",
    "calendario": "calendario académico, fechas y períodos",
}

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434")
).rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
ROUTER_TIMEOUT = max(5, int(os.getenv("OLLAMA_ROUTER_TIMEOUT_SECONDS", "20")))
ANSWER_TIMEOUT = max(15, int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")))
TOP_K = max(1, int(os.getenv("RAG_K", "3")))
MAX_CONTEXT_CHARS = max(2500, int(os.getenv("RAG_MAX_CONTEXT_CHARS", "9000")))


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto).casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _tokens(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalizar(texto)))


# Las reglas cubren preguntas frecuentes cuando Ollama no está disponible.
# Cada intención se enlaza con carpetas dinámicas por su nombre o por una
# muestra de los documentos cargados. Carpetas nuevas siguen siendo elegibles
# para el router gracias a la descripción que se construye con su contenido.
INTENT_RULES = (
    {
        "id": "horarios",
        "question": ("horario", "horarios", "a que hora", "que dias", "que dia",
                     "dias de clase", "cuando hay clase", "cuando curso",
                     "presencial", "presencialidad", "turno", "salon", "aula",
                     "horas de clase"),
        "names": ("horario", "horarios", "cursada", "agenda", "presencialidad",
                  "presencialidades", "turno", "aula", "aulas"),
        "content": ("horario", "horarios", "lunes", "martes", "miercoles",
                    "jueves", "viernes", "presencialidad", "turno"),
    },
    {
        "id": "docentes",
        "question": ("profesor", "profesora", "profe", "docente", "quien dicta",
                     "quien da", "mail del docente", "correo del profesor"),
        "names": ("docente", "docentes", "profesor", "profesores", "catedra",
                  "catedras", "equipo docente"),
        "content": ("docente:", "dicta:", "profesor", "profesora", "catedra"),
    },
    {
        "id": "parciales",
        "question": ("parcial", "parciales", "examen", "examenes", "evaluacion",
                     "evaluaciones", "prueba", "fecha de examen"),
        "names": ("parcial", "parciales", "examen", "examenes", "evaluacion",
                  "evaluaciones", "prueba", "pruebas"),
        "content": ("parcial", "examen", "evaluacion", "evaluaciones"),
    },
    {
        "id": "perfil_ingreso",
        "question": ("perfil de ingreso", "perfil ingreso", "para ingresar",
                     "requisitos de ingreso", "requisito para ingresar",
                     "como ingreso", "como puedo ingresar", "ingresar a la carrera",
                     "necesito para entrar", "puedo entrar a la carrera",
                     "ficha de ingreso", "que necesito para ingresar",
                     "necesito para ingresar", "entrar a la carrera"),
        "names": ("perfil ingreso", "ingreso", "admisiones", "requisitos"),
        "content": ("perfil de ingreso", "requisitos de ingreso", "via de ingreso",
                    "bachillerato", "ingresar a la carrera"),
    },
    {
        "id": "perfil_egreso",
        "question": ("perfil de egreso", "perfil egreso", "perfil de engreso",
                     "perfil engreso", "al egresar", "cuando egrese",
                     "competencias al egresar", "al terminar la carrera",
                     "al finalizar la carrera"),
        "names": ("perfil egreso", "egreso", "egresados", "competencias"),
        "content": ("perfil de egreso", "competencias al egresar", "al egresar"),
    },
    {
        "id": "info_general",
        "question": ("puntaje", "puntos", "nota minima", "nota", "exonerar",
                     "exoneracion", "aprobar", "aprobacion", "reprobar",
                     "derecho a examen", "normativa", "reglamento"),
        "names": ("info general", "informacion general", "normativa", "reglamento",
                  "evaluacion general", "puntajes", "aprobacion"),
        "content": ("puntaje", "exoneracion", "nota", "aprobacion", "reglamento"),
    },
    {
        "id": "calendario",
        "question": ("calendario", "feriado", "feriados", "inicio de clases",
                     "cuando empiezan las clases", "periodo lectivo"),
        "names": ("calendario", "fechas academicas", "cronograma"),
        "content": ("calendario academico", "feriado", "inicio de clases"),
    },
    {
        "id": "materias",
        "question": ("programa de", "temario", "previatura", "previaturas",
                     "prerrequisito", "creditos", "plan de estudio",
                     "que se estudia", "que materias", "que asignaturas",
                     "materias del semestre", "contenido de la materia"),
        "names": ("materias", "asignaturas", "cursos", "planes de estudio",
                  "programas"),
        "content": ("programa de la asignatura", "previatura", "creditos",
                    "objetivo de la asignatura", "contenido tematico"),
    },
)


def _endpoint() -> str:
    if OLLAMA_BASE_URL.endswith("/api/generate"):
        return OLLAMA_BASE_URL
    if OLLAMA_BASE_URL.endswith("/api"):
        return OLLAMA_BASE_URL + "/generate"
    return OLLAMA_BASE_URL + "/api/generate"


def _llamar_ollama(prompt: str, *, json_mode: bool = False):
    etapa = "ROUTER" if json_mode else "SINTESIS"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 220 if json_mode else max(250, int(os.getenv("OLLAMA_NUM_PREDICT", "400"))),
        },
    }
    if json_mode:
        body["format"] = "json"
    if OLLAMA_MODEL.casefold().startswith("gemma4"):
        body["think"] = False

    timeout = ROUTER_TIMEOUT if json_mode else ANSWER_TIMEOUT
    response = requests.post(
        _endpoint(),
        json=body,
        timeout=(5, timeout),
    )
    if not response.ok:
        detail = re.sub(r"\s+", " ", response.text).strip()[:240]
        status = response.status_code
        response.close()
        print(f"[OLLAMA:{etapa}] HTTP {status}: {detail or 'sin detalle'}")
        raise RuntimeError(f"Ollama HTTP {status}: {detail or 'respuesta sin detalle'}")
    return response


def _category_name(category: str) -> str:
    return _normalizar(category.replace("_", " ").replace("-", " "))


def _category_profile(category: str, agent=None) -> str:
    description = AGENTES.get(category.casefold(), "")
    if agent is not None:
        files = " ".join(getattr(agent, "files_loaded", [])[:8])
        preview = getattr(agent, "category_preview", "")
        description = f"{description} {files} {preview}"
    return _normalizar(description)


def _category_match(category: str, agent, rule: dict) -> int:
    name = _category_name(category)
    profile = _category_profile(category, agent)
    name_hints = [_normalizar(value) for value in rule["names"]]
    content_hints = [_normalizar(value) for value in rule["content"]]
    score = 0
    for hint in name_hints:
        if hint and (hint == name or hint in name):
            score += 4
    for hint in content_hints:
        if hint and hint in profile:
            score += 1
    return score


def _detectar_intenciones(pregunta: str) -> list[dict]:
    q = _normalizar(pregunta)
    ingreso = any(term in q for term in (
        "perfil de ingreso", "perfil ingreso", "requisitos de ingreso",
        "para ingresar", "ingresar a la carrera", "examen de ingreso",
    ))
    egreso = any(term in q for term in (
        "perfil de egreso", "perfil egreso", "perfil de engreso",
        "perfil engreso", "al egresar", "al terminar la carrera",
        "al finalizar la carrera",
    ))

    found = []
    for rule in INTENT_RULES:
        if rule["id"] == "parciales" and ingreso:
            continue
        if any(_normalizar(term) in q for term in rule["question"]):
            found.append(rule)
    if ingreso and not any(rule["id"] == "perfil_ingreso" for rule in found):
        found.append(next(rule for rule in INTENT_RULES if rule["id"] == "perfil_ingreso"))
    if egreso and not any(rule["id"] == "perfil_egreso" for rule in found):
        found.append(next(rule for rule in INTENT_RULES if rule["id"] == "perfil_egreso"))

    # Las consultas sobre nota/exoneración de un parcial requieren las reglas
    # generales y el documento de evaluaciones, si ambas carpetas existen.
    if any(term in q for term in ("puntaje", "puntos", "exoner", "aprobar", "aprobacion",
                                   "reprobar", "derecho a examen", "nota")) and not ingreso:
        if not any(rule["id"] == "info_general" for rule in found):
            found.append(next(rule for rule in INTENT_RULES if rule["id"] == "info_general"))
        if any(term in q for term in ("parcial", "examen", "prueba")):
            if not any(rule["id"] == "parciales" for rule in found):
                found.append(next(rule for rule in INTENT_RULES if rule["id"] == "parciales"))
    return found


def _canonical_category(raw: str, categories: Mapping[str, object]) -> str | None:
    normalized = _category_name(raw)
    for category in categories:
        if _category_name(str(category)) == normalized:
            return str(category)
    return None


def _forced_routes(pregunta: str, categories: Mapping[str, object]) -> tuple[list[dict], list[str], bool]:
    intents = _detectar_intenciones(pregunta)
    selected: dict[str, dict] = {}
    unavailable: list[str] = []

    for rule in intents:
        candidates = [
            (score, str(category))
            for category, agent in categories.items()
            if (score := _category_match(str(category), agent, rule)) > 0
        ]
        if not candidates:
            unavailable.append(rule["id"])
            continue
        best_score = max(score for score, _ in candidates)
        # Permite fusionar evidencia de dos carpetas que realmente describan
        # la misma categoría, pero evita enviar la pregunta a todos los agentes.
        for score, category in candidates:
            if score == best_score:
                selected.setdefault(category, {
                    "categoria": category,
                    "consulta": pregunta[:300],
                })

    return list(selected.values()), unavailable, bool(intents)


def _parsear_consultas(texto: str, pregunta: str, categories: Mapping[str, object]) -> list[dict]:
    match = re.search(r"\{[\s\S]*\}", texto)
    payload = json.loads(match.group(0) if match else texto)
    proposed = payload.get("consultas", payload.get("categorias", []))
    if not isinstance(proposed, list):
        raise ValueError("La clasificación de Ollama no contiene una lista")
    validated: dict[str, dict] = {}
    for item in proposed:
        if isinstance(item, str):
            item = {"categoria": item, "consulta": pregunta}
        if not isinstance(item, dict):
            continue
        raw_category = str(item.get("categoria", "")).strip()
        category = _canonical_category(raw_category, categories)
        if category is None:
            continue
        query = item.get("consulta", pregunta)
        if not isinstance(query, str) or not query.strip():
            query = pregunta
        validated.setdefault(category, {"categoria": category, "consulta": query.strip()[:300]})

    forced, _, has_intent = _forced_routes(pregunta, categories)
    # Las señales explícitas del alumno prevalecen sobre una ruta al azar del
    # modelo. Si no se reconoce la intención, se conserva la selección de IA.
    return forced if has_intent else list(validated.values())


def _local_fallback(pregunta: str, categories: Mapping[str, object]) -> list[dict]:
    forced, _, has_intent = _forced_routes(pregunta, categories)
    if has_intent:
        return forced

    ranked: list[tuple[float, str]] = []
    for category, agent in categories.items():
        try:
            results = agent.search_with_source(pregunta, top_k=1)
        except Exception as error:
            print(f"[BUSQUEDA:{category}] {type(error).__name__}: {error}")
            results = []
        score = float(results[0]["score"]) if results else 0.0
        name_terms = _tokens(str(category).replace("_", " "))
        overlap = len(name_terms & _tokens(pregunta))
        ranked.append((score + overlap, str(category)))
    ranked.sort(reverse=True)
    return [
        {"categoria": category, "consulta": pregunta[:300]}
        for score, category in ranked[:2]
        if score > 0
    ]


def clasificar(
    pregunta: str,
    categories: Mapping[str, object] | Iterable[str] | None = None,
) -> tuple[list[dict], str | None]:
    """Elige categorías disponibles en tiempo de ejecución, sin lista fija.

    Puede llamarse con los agentes ya cargados o, por compatibilidad, solo con
    la pregunta; en ese caso descubre las subcarpetas de backend/Documentos.
    """
    if categories is None:
        root = os.getenv("DOCUMENTOS_DIR")
        if root:
            from pathlib import Path
            documents_root = Path(root)
            if not documents_root.is_absolute():
                documents_root = Path(__file__).resolve().parent / documents_root
        else:
            documents_root = Path(__file__).resolve().parent / "Documentos"
        categories = {path.name: None for path in sorted(documents_root.iterdir()) if path.is_dir()} if documents_root.is_dir() else {}
    elif not isinstance(categories, Mapping):
        categories = {str(category): None for category in categories}

    if not categories:
        return [], "No hay carpetas de categorías en Documentos."

    descriptors = []
    for category, agent in categories.items():
        description = _category_profile(str(category), agent)
        descriptors.append(f"- {category}: {description[:420] or 'documentos de esta categoría'}")
    prompt = f"""Clasifica la pregunta de un estudiante universitario. No la respondas.
Selecciona solo las carpetas que contengan evidencia necesaria para responder.
Una pregunta con varios pedidos puede necesitar varias carpetas. No inventes categorías.
Si ningún directorio sirve, devuelve una lista vacía.
Categorías disponibles, generadas desde las carpetas actuales:
{chr(10).join(descriptors)}
Formato JSON: {{"consultas":[{{"categoria":"nombre exacto de carpeta","consulta":"búsqueda corta"}}]}}
Pregunta: {pregunta}"""

    try:
        response = _llamar_ollama(prompt, json_mode=True)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Ollama devolvió un cuerpo no JSON") from error
        finally:
            response.close()
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(str(payload.get("error", "respuesta inesperada")) if isinstance(payload, dict) else "respuesta inesperada")
        text = str(payload.get("response") or "").strip()
        if not text:
            raise RuntimeError("Ollama devolvió una clasificación vacía")
        return _parsear_consultas(text, pregunta, categories), None
    except Exception as error:
        detail = f"{type(error).__name__}: " + re.sub(r"\s+", " ", str(error)).strip()[:180]
        print(f"[ROUTER] Ollama no clasificó; uso rutas locales ({detail})")
        return _local_fallback(pregunta, categories), detail


def _buscar(
    agents: Mapping[str, object],
    consultas: list[dict],
    materia_aliases: list[str] | None = None,
) -> list[dict]:
    if not consultas:
        return []

    def buscar(item: dict) -> dict:
        category = item["categoria"]
        agent = agents.get(category)
        if agent is None:
            return {"categoria": category, "consulta": item["consulta"], "fragmentos": []}
        try:
            fragments = agent.search_with_source(
                item.get("consulta") or "",
                top_k=TOP_K,
                must_contain=materia_aliases,
            )
        except Exception as error:
            print(f"[BUSQUEDA:{category}] {type(error).__name__}: {error}")
            fragments = []
        return {"categoria": category, "consulta": item.get("consulta", ""), "fragmentos": fragments}

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(consultas), 8)) as pool:
        futures = [pool.submit(buscar, item) for item in consultas]
        for future in as_completed(futures):
            result = future.result()
            results[result["categoria"]] = result
    return [results[item["categoria"]] for item in consultas if item["categoria"] in results]


def _evidencia(results: list[dict]) -> tuple[str, list[str]]:
    parts: list[str] = []
    sources: list[str] = []
    used = 0
    for result in results:
        category_parts = []
        for index, fragment in enumerate(result.get("fragmentos", []), 1):
            source = fragment.get("fuente") or result["categoria"]
            source = str(source)
            sources.append(source)
            text = re.sub(r"\s+", " ", str(fragment.get("chunk", ""))).strip()
            block = f"[{result['categoria']} | {source} | evidencia {index}]\n{text[:1500]}"
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            category_parts.append(block)
            used += len(block)
        if category_parts:
            parts.append("\n".join(category_parts))
    return "\n\n".join(parts), sorted(set(sources))


def _respaldo(results: list[dict], unavailable: list[str] | None = None) -> str:
    """Respuesta de contingencia compacta si el modelo de síntesis falla."""
    lines = []
    seen = set()
    for result in results:
        for fragment in result.get("fragmentos", [])[:2]:
            text = re.sub(r"\s+", " ", str(fragment.get("chunk", ""))).strip()
            key = _normalizar(text)
            if not text or key in seen:
                continue
            seen.add(key)
            excerpt = text[:420].rstrip()
            if len(text) > len(excerpt):
                excerpt += "…"
            lines.append(f"- {excerpt} ({fragment.get('fuente', result['categoria'] )})")
    if not lines:
        if unavailable:
            return "Todavía no hay documentos cargados para responder sobre: " + ", ".join(unavailable) + "."
        return "No encontré información relacionada en los documentos cargados."
    return (
        "No pude completar la redacción con Ollama. Encontré esta evidencia breve:\n"
        + "\n".join(lines)
    )


def responder_stream(
    pregunta: str,
    agentes: Mapping[str, object],
    materia_aliases: list[str] | None = None,
) -> Iterable[str]:
    consultas, error_router = clasificar(pregunta, agentes)
    print("[ROUTER] " + (", ".join(item["categoria"] for item in consultas) or "sin categoría disponible"))

    if not consultas:
        forced, unavailable, has_intent = _forced_routes(pregunta, agentes)
        if has_intent and unavailable:
            yield "Todavía no hay documentos cargados para responder sobre: " + ", ".join(unavailable) + "."
        else:
            yield "No encontré una carpeta de documentos pertinente para esa pregunta."
        return

    results = _buscar(agentes, consultas, materia_aliases)
    evidence, sources = _evidencia(results)
    if not evidence:
        missing = [
            item["categoria"] for item in results
            if not item.get("fragmentos")
        ]
        if missing:
            yield "No encontré información pertinente en los archivos de estas categorías: " + ", ".join(missing) + "."
        else:
            yield "No encontré información pertinente en los documentos cargados."
        return

    _, unavailable, _ = _forced_routes(pregunta, agentes)
    missing_categories = [
        f"{name} (todavía no hay una carpeta/documentos para esa categoría)"
        for name in unavailable
    ]
    missing_note = (
        "\nPedidos que no tienen una carpeta disponible: " + ", ".join(missing_categories)
        if missing_categories else ""
    )

    prompt = f"""Eres el asistente académico de Tecnólogo en Informática. Redacta para el estudiante en español claro y natural.
Responde cada parte preguntada, con brevedad. Usa solamente la evidencia incluida abajo.
No copies bloques enteros ni inventes fechas, materias, docentes o reglas.
Si las fuentes muestran datos contradictorios, explica con precisión qué dice cada una.
Si la evidencia no alcanza para una parte, dilo claramente y aun así responde las demás.
No confundas horarios de clase con fechas de parciales ni con fechas de exámenes.
No supongas el mes o año si el documento no lo indica.
No uses encabezados repetidos. Añade al final una sola línea "Fuentes: ..." con los archivos consultados.

Pregunta: {pregunta}

Evidencia recuperada:
{evidence}
{missing_note}

Escribe la respuesta final al estudiante:"""

    response = None
    try:
        response = _llamar_ollama(prompt)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Ollama respondió con un cuerpo que no es JSON") from error
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(str(payload.get("error", "respuesta inesperada")) if isinstance(payload, dict) else "respuesta inesperada")
        answer = str(payload.get("response") or "").strip()
        done = payload.get("done") is True
        reason = str(payload.get("done_reason", "sin detalle"))
        if not done or not answer:
            thinking_len = len(str(payload.get("thinking") or ""))
            print(
                f"[OLLAMA:SINTESIS] generación incompleta: done={payload.get('done')!r}; "
                f"motivo={reason}; texto={len(answer)} caracteres; thinking={thinking_len}"
            )
            raise RuntimeError("Ollama no terminó una respuesta de texto")
    except Exception as error:
        print(f"[SINTESIS] Ollama no completó la respuesta: {type(error).__name__}: {error}")
        yield _respaldo(results, unavailable)
        return
    finally:
        if response is not None:
            response.close()

    if sources:
        answer = re.sub(r"\n*Fuentes:\s*.*$", "", answer, flags=re.IGNORECASE | re.DOTALL).strip()
        answer += "\n\nFuentes: " + ", ".join(sources)
    if error_router:
        print("[ROUTER] Se usó clasificación de respaldo local.")
    yield answer

