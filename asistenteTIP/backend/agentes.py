"""Enrutamiento dinámico y síntesis de evidencia con Ollama."""

from __future__ import annotations

import json
import os
import re
import unicodedata
import time
from pathlib import Path
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
DEBUG_FLOW = os.getenv("RAG_DEBUG_FLOW", "1").strip() != "0"
DEBUG_PROMPTS = os.getenv("RAG_DEBUG_PROMPTS", "1").strip() != "0"


def _limpiar_respuesta(texto: str) -> str:
    """Quita una sección de fuentes si el modelo la añade pese a las instrucciones."""
    texto = re.sub(
        r"(?im)(?:^|\s)(?:[-*•]\s*)?(?:\*\*)?(?:fuentes?(?:\s+consultadas?)?|sources?)\s*(?:\*\*)?\s*:.*$",
        "",
        texto,
    )
    # Red de seguridad: el modelo a veces cita "evidencia N" pese a la instrucción.
    texto = re.sub(r"(?im)^\s*(?:[-*•]\s*)?\**\s*seg[uú]n\s+(?:la\s+|el\s+|las\s+|los\s+)?(?:evidencias?|tablas?|fuentes?)\s*\d*\s*:?\s*\**\s*:?\s*$", "", texto)
    texto = re.sub(r"(?i)\s*\(\s*(?:seg[uú]n|de|en)\s+(?:la\s+|el\s+|las\s+|los\s+)?(?:primera\s+|segunda\s+|tercera\s+)?(?:evidencias?|tablas?|fuentes?)(?:\s+\d+)?(?:\s*(?:y|o|,)\s*(?:la\s+)?(?:evidencias?\s+)?\d+)*\s*\)", "", texto)
    texto = re.sub(r"(?i),?\s*seg[uú]n\s+(?:la\s+|el\s+)?(?:evidencias?|tablas?|fuentes?)\s+\d+", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


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
                     "quien da", "dicta", "dictan", "quien lo da", "quien la da",
                     "a cargo", "mail del docente", "correo del profesor"),
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


def _llamar_ollama(prompt: str, *, json_mode: bool = False, num_predict: int | None = None):
    etapa = "ROUTER" if json_mode else "SINTESIS"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 220 if json_mode else (num_predict or max(250, int(os.getenv("OLLAMA_NUM_PREDICT", "400")))),
        },
    }
    if json_mode:
        body["format"] = "json"
    if OLLAMA_MODEL.casefold().startswith("gemma4"):
        body["think"] = False

    timeout = ROUTER_TIMEOUT if json_mode else ANSWER_TIMEOUT
    etapa_label = "ROUTER" if json_mode else "SINTESIS"
    started = time.perf_counter()
    if DEBUG_FLOW:
        print(
            f"[OLLAMA:{etapa_label}:INICIO] modelo={OLLAMA_MODEL} "
            f"timeout={timeout}s prompt={len(prompt)} caracteres",
            flush=True,
        )
    if DEBUG_PROMPTS:
        print(f"[OLLAMA:{etapa_label}:PROMPT]\n{prompt}\n[/{etapa_label}:PROMPT]", flush=True)

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
    if DEBUG_FLOW:
        elapsed = time.perf_counter() - started
        print(f"[OLLAMA:{etapa_label}:HTTP] status={response.status_code} | latencia={elapsed:.2f}s", flush=True)
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

def _es_consulta_general_materias(pregunta: str) -> bool:
    q = _normalizar(pregunta)
    # Pedidos de horarios, parciales o docentes se resuelven en sus propias carpetas.
    if re.search(r"horario|parcial|examen|profesor|profe\b|docente|dicta|previatura|credito|programa de", q):
        return False
    general = any(termino in q for termino in (
        "que materias hay", "que materias tiene", "todas las materias",
        "plan de estudios", "materias de la carrera", "materias hay en la carrera",
        "que se estudia", "materias por semestre", "lista de materias",
        "que asignaturas", "cuantas materias",
    ))
    # "carre\w*" tolera errores de tipeo como "carrear".
    plural = re.search(r"\b(materias|asignaturas|cursos)\b", q)
    contexto = re.search(
        r"\b(carre\w*|plan|todas?|todo|lista|listado|semestres|cuantas|total|completo|completa|existen|transcurso)\b", q
    )
    return bool(
        general
        or (plural and contexto)
        or (
            "semestre" in q
            and any(termino in q for termino in ("materia", "asignatura", "curso", "cuantas", "cantidad"))
        )
    )


def _indice_materias(pregunta: str) -> tuple[str, str] | None:
    """Recupera del índice estático todas las secciones de semestre solicitadas."""
    raiz = Path(__file__).resolve().parent / "data" / "processed" / "cursos"
    archivo = next((p for p in (raiz / "indice_materias.txt", raiz / "contenido.txt") if p.is_file()), None)
    if archivo is None:
        return None
    try:
        texto = archivo.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        print(f"[CATALOGO] No se pudo leer {archivo}: {error}", flush=True)
        return None

    nombres = ("Primer", "Segundo", "Tercer", "Cuarto", "Quinto", "Sexto")
    titulos = re.compile(r"(?im)^\s*(Primer|Segundo|Tercer|Cuarto|Quinto|Sexto)\s+Semestre\s*$")
    encabezados = list(titulos.finditer(texto))
    if not encabezados:
        return None
    consulta = _normalizar(pregunta)
    alias = (
        "primer|primero|1er|1ro|1", "segundo|2do|2", "tercer|tercero|3er|3ro|3",
        "cuarto|4to|4", "quinto|5to|5", "sexto|6to|6",
    )
    pedidos = [i for i, formas in enumerate(alias, 1)
               if re.search(rf"(?<!\w)(?:{formas})(?!\w)", consulta)]
    if not pedidos:
        pedidos = list(range(1, 7))
    bloques = []
    for i, encabezado in enumerate(encabezados):
        numero = nombres.index(encabezado.group(1).title()) + 1
        if numero not in pedidos:
            continue
        fin = encabezados[i + 1].start() if i + 1 < len(encabezados) else len(texto)
        materias = re.findall(r"(?m)^\s*[-*•]\s*(.+?)\s*$", texto[encabezado.end():fin])
        if materias:
            bloques.append(f"{nombres[numero - 1]} Semestre\n" + "\n".join(f"- {m}" for m in materias))
    if not bloques:
        return None
    return str(archivo), "\n\n".join(bloques)

def _canonical_category(raw: str, categories: Mapping[str, object]) -> str | None:
    normalized = _category_name(raw)
    for category in categories:
        if _category_name(str(category)) == normalized:
            return str(category)
    return None


def _pregunta_amplia(pregunta: str) -> bool:
    """Pedidos de un semestre completo o de todo un listado necesitan más fragmentos."""
    q = _normalizar(pregunta)
    return bool(re.search(r"\b(semestre|semestres|todos|todas|todo|completo|completa|toda la semana)\b", q))


# Si no existe una carpeta propia para la intención, estas otras sí contienen la respuesta
# (la leyenda "Materia – Docente" de horarios y el "Docente:" de cada programa).
INTENT_FALLBACKS = {"docentes": ("horarios", "materias")}


def _forced_routes(pregunta: str, categories: Mapping[str, object]) -> tuple[list[dict], list[str], bool]:
    intents = _detectar_intenciones(pregunta)
    selected: dict[str, dict] = {}
    unavailable: list[str] = []
    amplia = _pregunta_amplia(pregunta)
    rules_by_id = {rule["id"]: rule for rule in INTENT_RULES}

    def candidates_for(rule: dict) -> list[tuple[int, str]]:
        return [
            (score, str(category))
            for category, agent in categories.items()
            if (score := _category_match(str(category), agent, rule)) > 0
        ]

    def select(rule: dict, candidates: list[tuple[int, str]]) -> None:
        best_score = max(score for score, _ in candidates)
        # Permite fusionar evidencia de dos carpetas que realmente describan
        # la misma categoría, pero evita enviar la pregunta a todos los agentes.
        for score, category in candidates:
            if score == best_score:
                item = selected.setdefault(category, {
                    "categoria": category,
                    "consulta": pregunta[:300],
                })
                if amplia and rule["id"] in {"horarios", "parciales"}:
                    item["top_k"] = 8

    for rule in intents:
        candidates = candidates_for(rule)
        if candidates:
            select(rule, candidates)
        elif rule["id"] not in INTENT_FALLBACKS:
            unavailable.append(rule["id"])
        # Los docentes también salen de la leyenda de horarios y de los programas de cada materia.
        if rule["id"] in INTENT_FALLBACKS:
            found_fallback = False
            for fallback_id in INTENT_FALLBACKS[rule["id"]]:
                fallback_candidates = candidates_for(rules_by_id[fallback_id])
                if fallback_candidates:
                    select(rules_by_id[fallback_id], fallback_candidates)
                    found_fallback = True
            if not candidates and not found_fallback:
                unavailable.append(rule["id"])

    if _es_consulta_general_materias(pregunta):
        categoria_cursos = next(
            (c for c in categories if _category_name(c) in {"cursos", "materias"}),
            None,
        )
        if categoria_cursos:
            selected[categoria_cursos] = {
                "categoria": categoria_cursos,
                "consulta": pregunta[:300],
                "solo_raiz": True,
            }

    return list(selected.values()), unavailable, bool(intents) or _es_consulta_general_materias(pregunta)


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
    if DEBUG_FLOW:
        print(f"[ROUTER:ENTRADA] pregunta={pregunta} | categorías={', '.join(categories)}", flush=True)
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
        if DEBUG_FLOW:
            print(f"[OLLAMA:ROUTER:SALIDA]\n{text}", flush=True)
        selected = _parsear_consultas(text, pregunta, categories)
        if DEBUG_FLOW:
            print("[ROUTER:SELECCION] " + (", ".join(item["categoria"] for item in selected) or "sin categoría"), flush=True)
        return selected, None
    except Exception as error:
        detail = f"{type(error).__name__}: " + re.sub(r"\s+", " ", str(error)).strip()[:180]
        print(f"[ROUTER] Ollama no clasificó; uso rutas locales ({detail})")
        return _local_fallback(pregunta, categories), detail


def _buscar(
    agents: Mapping[str, object],
    consultas: list[dict],
    materia_aliases: list[str] | None = None,
    materia_preferida: list[str] | None = None,
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
                top_k=item.get("top_k", TOP_K),
                must_contain=materia_aliases,
                solo_raiz=item.get("solo_raiz", False),
                prefer=materia_preferida,
            )
        except Exception as error:
            print(f"[BUSQUEDA:{category}] {type(error).__name__}: {error}")
            fragments = []
        if DEBUG_FLOW:
            print(
                f"[BUSQUEDA:{category}] consulta={item.get('consulta', '')!r} "
                f"| resultados={len(fragments)}",
                flush=True,
            )
            for index, fragment in enumerate(fragments, 1):
                source = fragment.get("fuente") or category
                score = fragment.get("score", "n/d")
                text = re.sub(r"\s+", " ", str(fragment.get("chunk", ""))).strip()
                print(
                    f"[EVIDENCIA:{category}:{index}] archivo={source} | score={score} "
                    f"| texto={text[:700]}",
                    flush=True,
                )
        return {"categoria": category, "consulta": item.get("consulta", ""), "fragmentos": fragments}

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(consultas), 8)) as pool:
        futures = [pool.submit(buscar, item) for item in consultas]
        for future in as_completed(futures):
            result = future.result()
            results[result["categoria"]] = result
    return [results[item["categoria"]] for item in consultas if item["categoria"] in results]


def _evidencia(results: list[dict], incluir_apoyos: bool = True) -> tuple[str, list[str]]:
    parts: list[str] = []
    sources: list[str] = []
    used = 0
    for result in results:
        category_parts = []
        for index, fragment in enumerate(result.get("fragmentos", []), 1):
            source = fragment.get("fuente") or result["categoria"]
            source = str(source)
            sources.append(source)
            raw = str(fragment.get("chunk", ""))
            if not incluir_apoyos:
                # Los horarios de "Apoyo ..." no son clases; solo se envían si se preguntan.
                raw = "\n".join(line for line in raw.splitlines() if not line.lstrip().lower().startswith("apoyo"))
            text = re.sub(r"\s+", " ", raw).strip()
            if not text:
                continue
            block = f"[{result['categoria']} | {source} | evidencia {index}]\n{text[:1500]}"
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            category_parts.append(block)
            used += len(block)
        if category_parts:
            parts.append("\n".join(category_parts))
    return "\n\n".join(parts), sorted(set(sources))


def _respaldo(results: list[dict], unavailable: list[str] | None = None) -> str:
    """Mensaje legible si Ollama no logra sintetizar; la evidencia queda en consola."""
    return "Encontré información relacionada, pero no pude redactar una respuesta ahora. Inténtalo de nuevo en unos segundos."

def responder_stream(
    pregunta: str,
    agentes: Mapping[str, object],
    materia_aliases: list[str] | None = None,
    historial: list[dict] | None = None,
    materia_preferida: list[str] | None = None,
) -> Iterable[str]:
    if DEBUG_FLOW:
        print(f"[FLUJO:INICIO] pregunta={pregunta}", flush=True)
    consultas, error_router = clasificar(pregunta, agentes)
    print("[ROUTER] " + (", ".join(item["categoria"] for item in consultas) or "sin categoría disponible"))

    if not consultas:
        forced, unavailable, has_intent = _forced_routes(pregunta, agentes)
        if has_intent and unavailable:
            yield "Todavía no hay documentos cargados para responder sobre: " + ", ".join(unavailable) + "."
        else:
            yield "No encontré una carpeta de documentos pertinente para esa pregunta."
        return

    catalogo = _indice_materias(pregunta) if _es_consulta_general_materias(pregunta) else None
    if catalogo:
        ruta_indice, texto_indice = catalogo
        consultas_adicionales = [
            item for item in consultas
            if _category_name(item.get("categoria", "")) not in {"cursos", "materias"}
        ]
        results = _buscar(agentes, consultas_adicionales, materia_aliases, materia_preferida)
        results.insert(0, {
            "categoria": "cursos",
            "consulta": pregunta,
            "fragmentos": [{
                "chunk": texto_indice,
                "fuente": ruta_indice,
                "score": 1.0,
                "tipo_fuente": "static",
            }],
        })
        print(f"[CATALOGO:ESTATICO] archivo={ruta_indice} | secciones enviadas sin top_k", flush=True)
    else:
        results = _buscar(agentes, consultas, materia_aliases, materia_preferida)
    evidence, sources = _evidencia(results, incluir_apoyos="apoyo" in _normalizar(pregunta))
    if DEBUG_FLOW:
        count_fragments = sum(len(item.get("fragmentos", [])) for item in results)
        print(
            f"[BUSQUEDA:FIN] fragmentos={count_fragments} "
            f"| contexto={len(evidence)} caracteres | archivos={', '.join(sources) or 'ninguno'}",
            flush=True,
        )
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
    bloque_historial = ""
    if historial:
        turnos = "\n".join(
            f"Estudiante: {turno['pregunta']}\nAsistente: {turno['respuesta']}"
            for turno in historial[-5:]
        )
        bloque_historial = f"\nConversación reciente (de más antigua a más nueva):\n{turnos}\n"

    instruccion_indice = (
        "La evidencia del índice es completa para los semestres pedidos. Enumera todas sus materias, "
        "sin omitir semestres ni asignaturas; si el historial contradice el índice, usa el índice actual.\n"
        if catalogo else ""
    )

    prompt = f"""Eres el asistente académico de Tecnólogo en Informática. Redacta para el estudiante en español claro y natural.
    Responde cada parte preguntada, con brevedad. Usa solamente la evidencia incluida abajo.
    {instruccion_indice}
    No copies bloques enteros ni inventes fechas, materias, docentes o reglas.
    Si dos fragmentos dicen lo mismo, menciona el dato una sola vez. Si se contradicen de verdad, explica con precisión qué dice cada uno.
    Si la evidencia no alcanza para una parte, dilo claramente y aun así responde las demás.
    No confundas horarios de clase con fechas de parciales ni con fechas de exámenes. Los "Apoyo ..." no son clases: menciónalos solo si te los piden.
    No supongas el mes o año si el documento no lo indica.
    Si piden un semestre o varias materias, responde una línea por materia, sin omitir ninguna que aparezca en la evidencia.
    Si hay varios docentes para una materia, menciónalos a todos.
    Si la evidencia no menciona lo que preguntan, dilo en una frase y no listes otros datos que no pidieron.
    Nunca escribas "según la evidencia", "evidencia 1", "primera tabla", "fuente" ni nombres de archivos. No uses encabezados repetidos.

    {bloque_historial}
    Pregunta: {pregunta}

    Evidencia recuperada:
    {evidence}
    {missing_note}

    Escribe la respuesta final al estudiante:"""

    response = None
    try:
        response = _llamar_ollama(prompt, num_predict=900 if _pregunta_amplia(pregunta) else None)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Ollama respondió con un cuerpo que no es JSON") from error
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(str(payload.get("error", "respuesta inesperada")) if isinstance(payload, dict) else "respuesta inesperada")
        answer = str(payload.get("response") or "").strip()
        done = payload.get("done") is True
        reason = str(payload.get("done_reason", "sin detalle"))
        if DEBUG_FLOW:
            print(f"[OLLAMA:SINTESIS:METADATOS] done={done} | motivo={reason} | eval_count={payload.get('eval_count', 'n/d')}", flush=True)
            print(f"[OLLAMA:SINTESIS:SALIDA]\n{answer}", flush=True)
        if not done or not answer:
            thinking_len = len(str(payload.get("thinking") or ""))
            print(
                f"[OLLAMA:SINTESIS] generación incompleta: done={payload.get('done')!r}; "
                f"motivo={reason}; texto={len(answer)} caracteres; thinking={thinking_len}"
            )
            raise RuntimeError("Ollama no terminó una respuesta de texto")
    except Exception as error:
        print(f"[SINTESIS] Ollama no completó la respuesta: {type(error).__name__}: {error}")
        if DEBUG_FLOW:
            print("[SINTESIS:RESPALDO] Se devuelve el mensaje temporal; la evidencia ya quedó registrada arriba.", flush=True)
        yield _respaldo(results, unavailable)
        return
    finally:
        if response is not None:
            response.close()

    answer = _limpiar_respuesta(answer)
    if DEBUG_FLOW:
        print(f"[RESPUESTA:WEB]\n{answer}", flush=True)
    if error_router:
        print("[ROUTER] Se usó clasificación de respaldo local.")
    yield answer

