"""Router y síntesis multiagente con Ollama para el backend TIP."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import requests


AGENTES = {
    "cursos": "programas, contenidos, asignaturas, previaturas y datos específicos de cada curso",
    "parciales": "fechas y evaluaciones parciales o exámenes de las materias",
    "perfil_ingreso": "requisitos y vías para ingresar a la carrera",
    "perfil_egreso": "competencias y capacidades al egresar",
    "horarios": "horarios de cursada, días, turnos, salones y presencialidades",
    "info_general": "información institucional, calendario y reglas generales de puntajes",
    "docentes": "nombres de docentes y asignaturas que dicta cada uno",
}

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434")
).rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
ROUTER_TIMEOUT = max(5, int(os.getenv("OLLAMA_ROUTER_TIMEOUT_SECONDS", "20")))
ANSWER_TIMEOUT = max(15, int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")))
TOP_K = max(1, int(os.getenv("RAG_K", "3")))


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _llamar_ollama(prompt: str, *, json_mode: bool = False, stream: bool = False):
    etapa = "ROUTER" if json_mode else "SINTESIS"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": 0,
            "num_predict": 180 if json_mode else 300,
        },
    }
    if json_mode:
        body["format"] = "json"
    elif OLLAMA_MODEL.casefold().startswith("gemma4"):
        # Para esta tarea de redacción no necesitamos el canal de razonamiento
        # de Gemma; pedimos directamente el texto final.
        body["think"] = False
    timeout = ROUTER_TIMEOUT if json_mode else ANSWER_TIMEOUT
    if OLLAMA_BASE_URL.endswith("/api/generate"):
        endpoint = OLLAMA_BASE_URL
    elif OLLAMA_BASE_URL.endswith("/api"):
        endpoint = OLLAMA_BASE_URL + "/generate"
    else:
        endpoint = OLLAMA_BASE_URL + "/api/generate"
    response = requests.post(
        endpoint,
        json=body,
        stream=stream,
        timeout=(5, timeout),
    )
    if not response.ok:
        detalle = re.sub(r"\s+", " ", response.text).strip()[:300]
        status = response.status_code
        response.close()
        print(f"[OLLAMA:{etapa}] HTTP {status}: {detalle or 'sin detalle'}")
        raise RuntimeError(f"Ollama HTTP {status}: {detalle or 'respuesta sin detalle'}")
    print(
        f"[OLLAMA:{etapa}] HTTP {response.status_code}; generación iniciada; "
        f"modelo={OLLAMA_MODEL}; stream={str(stream).lower()}"
    )
    return response


def _consulta(categoria: str, pregunta: str) -> str:
    focos = {
        "cursos": "programa, contenido, créditos y previaturas",
        "parciales": "parciales, examen, fechas y puntajes de evaluación",
        "perfil_ingreso": "perfil y requisitos de ingreso",
        "perfil_egreso": "perfil y competencias de egreso",
        "horarios": "horarios, días y presencialidad de clase",
        "info_general": "normativa, puntajes, notas y exoneración",
        "docentes": "docente y asignaturas que dicta",
    }
    return f"{focos[categoria]}. Consulta original: {pregunta[:220]}"


def _forzar_categorias(pregunta: str, propuestas: Iterable[dict]) -> list[dict[str, str]]:
    """Completa omisiones comunes del modelo y evita mezclar horarios con notas."""
    seleccion: dict[str, str] = {}
    for item in propuestas:
        if not isinstance(item, dict):
            continue
        categoria = item.get("categoria")
        subconsulta = item.get("consulta", "")
        if categoria in AGENTES and isinstance(subconsulta, str):
            seleccion.setdefault(categoria, subconsulta.strip()[:260] or _consulta(categoria, pregunta))

    q = _normalizar(pregunta)
    es_ingreso = any(x in q for x in (
        "perfil de ingreso", "perfil ingreso", "requisito para ingresar", "requisitos para ingresar",
        "requisitos de ingreso", "necesito para ingresar", "que necesito para ingresar",
        "ingresar a la carrera", "como ingreso", "como puedo ingresar",
        "via de ingreso", "examen de ingreso",
    ))
    es_egreso = any(x in q for x in (
        "perfil de egreso", "perfil egreso", "perfil de engreso", "perfil engreso",
        "al egresar", "cuando egrese", "competencias al egresar",
        "al terminar la carrera", "al finalizar la carrera", "cuando termine la carrera",
    ))
    evaluacion = not es_ingreso and any(x in q for x in (
        "parcial", "examen", "prueba", "evaluacion",
    ))
    puntajes = not es_ingreso and any(x in q for x in (
        "puntaje", "puntos", "punto", "nota", "exoner", "aprobar", "aprobo",
        "reprobar", "derecho a examen",
    ))
    horario = any(x in q for x in (
        "horario", "a que hora", "que dias", "que dia", "dias de clase",
        "turno", "salon", "presencial", "cursada", "horas de clase",
    ))
    docente = any(x in q for x in (
        "profesor", "profesora", "docente", "quien dicta", "quien da la materia",
    ))
    calendario = any(x in q for x in (
        "calendario", "feriado", "feriados", "fecha de inicio", "cuando empiezan las clases",
    ))
    curso = any(x in q for x in (
        "programa", "contenido", "temario", "previatura", "previaturas",
        "prerrequisito", "creditos", "plan de estudio", "que se estudia",
        "asignaturas de", "materias de", "hay materias", "matematica",
        "hay asignaturas", "presencialidad", "presencialidades", "asistencia",
    ))

    obligatorias = []
    if es_ingreso:
        # La palabra "examen" en el trámite de ingreso no alude a parciales.
        seleccion.pop("parciales", None)
        if not es_egreso:
            seleccion.pop("perfil_egreso", None)
        if not puntajes and not calendario:
            seleccion.pop("info_general", None)
    if es_egreso and not es_ingreso:
        # No permitir que un error del router convierta egreso en ingreso.
        seleccion.pop("perfil_ingreso", None)
    if es_ingreso:
        obligatorias.append("perfil_ingreso")
    if es_egreso:
        obligatorias.append("perfil_egreso")
    if evaluacion:
        obligatorias.append("parciales")
    if puntajes:
        obligatorias.append("info_general")
        if evaluacion:
            obligatorias.append("parciales")
    if horario:
        obligatorias.append("horarios")
        # Una pregunta de cursada debe llegar al corpus de horarios, no a la tabla general.
        if not puntajes and not calendario:
            seleccion.pop("info_general", None)
    if docente:
        obligatorias.append("docentes")
    if calendario:
        obligatorias.append("info_general")
    if curso:
        obligatorias.append("cursos")

    for categoria in obligatorias:
        seleccion.setdefault(categoria, _consulta(categoria, pregunta))

    if not seleccion:
        # Consulta ambigua: deja que los datos generales intenten resolverla.
        seleccion["info_general"] = _consulta("info_general", pregunta)

    return [
        {"categoria": categoria, "consulta": seleccion[categoria]}
        for categoria in AGENTES if categoria in seleccion
    ]


def _parsear_consultas(texto: str, pregunta: str) -> list[dict[str, str]]:
    bloque = re.search(r"\{[\s\S]*\}", texto)
    datos = json.loads(bloque.group() if bloque else texto)
    propuestas = datos.get("consultas", datos.get("categorias", []))
    if not isinstance(propuestas, list):
        raise ValueError("El router de Ollama no devolvió una lista de categorías")
    # Acepta también {"categorias":["horarios", ...]}.
    propuestas = [
        {"categoria": item, "consulta": _consulta(item, pregunta)} if isinstance(item, str) else item
        for item in propuestas
    ]
    return _forzar_categorias(pregunta, propuestas)


def clasificar(pregunta: str) -> tuple[list[dict[str, str]], str | None]:
    descripciones = "\n".join(f"- {key}: {value}" for key, value in AGENTES.items())
    prompt = f"""Clasifica la pregunta para un asistente universitario. No la respondas.
Elige TODAS las categorías que necesiten aportar evidencia y escribe una búsqueda breve para cada una.
Reglas: horarios de clase -> horarios; fechas de parciales -> parciales;
puntajes o exoneración -> info_general y, si se pregunta por parcial/examen, también parciales;
profesor -> docentes; ingreso -> perfil_ingreso; egreso -> perfil_egreso.
La palabra examen por sí sola no significa ingreso. No envíes horarios de clase a info_general.
Usa únicamente estos identificadores:
{descripciones}
Devuelve JSON con esta forma: {{"consultas":[{{"categoria":"horarios","consulta":"MDL1 horarios de clase"}}]}}
Pregunta: {pregunta}"""
    try:
        response = _llamar_ollama(prompt, json_mode=True, stream=False)
        text = response.json().get("response", "").strip()
        if not text:
            raise ValueError("Ollama devolvió una clasificación vacía")
        return _parsear_consultas(text, pregunta), None
    except Exception as error:
        # El fallback es deliberadamente corto y no depende de OpenRouter.
        detalle = f"{type(error).__name__}: " + re.sub(r"\s+", " ", str(error)).strip()[:180]
        print(f"[ROUTER] Ollama no clasificó; aplico reglas locales ({detalle or type(error).__name__})")
        return _forzar_categorias(pregunta, []), detalle or type(error).__name__


def _buscar(
    agentes: dict,
    consultas: list[dict[str, str]],
    materia_aliases: list[str] | None = None,
) -> list[dict]:
    resultados: dict[str, dict] = {}

    def buscar(item: dict) -> dict:
        categoria = item["categoria"]
        agente = agentes.get(categoria)
        if agente is None:
            return {"categoria": categoria, "consulta": item["consulta"], "fragmentos": []}
        try:
            restringir_materia = (
                materia_aliases
                if materia_aliases and categoria in {
                    "cursos", "parciales", "horarios", "docentes"
                }
                else None
            )
            fragmentos = agente.search_with_source(
                item["consulta"], top_k=TOP_K, must_contain=restringir_materia
            )
        except Exception as error:
            print(f"[BUSQUEDA:{categoria}] {type(error).__name__}: {error}")
            fragmentos = []
        return {"categoria": categoria, "consulta": item["consulta"], "fragmentos": fragmentos}

    if not consultas:
        return []
    with ThreadPoolExecutor(max_workers=min(len(consultas), 7)) as pool:
        pendientes = [pool.submit(buscar, item) for item in consultas]
        for futuro in as_completed(pendientes):
            resultado = futuro.result()
            resultados[resultado["categoria"]] = resultado
    return [resultados[c] for c in AGENTES if c in resultados]


def _evidencia(resultados: list[dict]) -> tuple[str, list[str]]:
    bloques: list[str] = []
    fuentes: list[str] = []
    limite_total = 12_000
    usados = 0
    for resultado in resultados:
        categoria = resultado["categoria"]
        fragmentos = resultado["fragmentos"]
        if not fragmentos:
            continue
        partes = []
        for n, fragmento in enumerate(fragmentos, 1):
            fuente = fragmento.get("fuente") or f"{categoria}.txt"
            fuentes.append(fuente)
            texto = re.sub(r"\s+", " ", fragmento["chunk"]).strip()[:1600]
            parte = f"[Fragmento {n}; categoría: {categoria}; fuente: {fuente}]\n{texto}"
            if usados + len(parte) > limite_total:
                break
            partes.append(parte)
            usados += len(parte)
        if partes:
            bloques.append(f"## {categoria}\n" + "\n\n".join(partes))
    return "\n\n".join(bloques), sorted(set(fuentes))


def _respaldo(resultados: list[dict], motivo: str | None = None) -> str:
    """Construye una respuesta completa con citas si Ollama falla."""
    lineas = []
    vistos = set()
    for resultado in resultados:
        if not resultado["fragmentos"]:
            continue
        for fragmento in resultado["fragmentos"][:2]:
            texto = re.sub(r"\s+", " ", fragmento["chunk"]).strip()
            clave = _normalizar(texto)
            if not texto or clave in vistos:
                continue
            vistos.add(clave)
            extracto = texto[:900]
            lineas.append(
                f"- **{resultado['categoria']}** "
                f"({fragmento.get('fuente', 'documento')}): {extracto}"
            )
    if not lineas:
        return "No encontré información pertinente en los documentos cargados."
    return "Respuesta tomada directamente de los documentos:\n" + "\n".join(lineas)


def responder_stream(
    pregunta: str,
    agentes: dict,
    materia_aliases: list[str] | None = None,
) -> Iterable[str]:
    consultas, error_router = clasificar(pregunta)
    print("[ROUTER] " + ", ".join(item["categoria"] for item in consultas))
    resultados = _buscar(agentes, consultas, materia_aliases)
    evidencia, fuentes = _evidencia(resultados)
    if not evidencia:
        yield "No encontré información pertinente en los documentos cargados."
        return

    prompt = f"""Eres el asistente académico de Tecnólogo en Informática. Redacta una respuesta final natural y clara en español.
Responde todas las partes de la pregunta usando únicamente la evidencia. No enumeres ni copies los fragmentos.
Organiza la respuesta en viñetas breves, una por dato pedido, por ejemplo: horario, docente y parciales.
Conserva exactamente los días, horas y fechas que aparecen en los documentos; no deduzcas mes ni año si no están escritos.
Si hay dos fechas posibles o una contradicción, explica brevemente qué muestran las fuentes sin inventar una resolución.
Si falta uno de los datos, responde los demás y aclara cuál no aparece. No agregues recomendaciones genéricas.

Pregunta: {pregunta}

Información encontrada por los agentes:
{evidencia}

Redacta ahora la respuesta para el alumno:"""

    response = None
    try:
        # La síntesis no se muestra token a token: responder_stream la retenía
        # hasta done=true. Una respuesta JSON completa evita depender del
        # cierre correcto del stream de Ollama.
        response = _llamar_ollama(prompt, stream=False)
        try:
            dato = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            cuerpo = re.sub(r"\s+", " ", response.text).strip()[:300]
            raise RuntimeError(
                f"Ollama devolvió HTTP 200 pero el cuerpo no es JSON: {cuerpo or 'vacío'}"
            ) from error

        if not isinstance(dato, dict):
            raise RuntimeError("Ollama devolvió un cuerpo JSON con formato inesperado")
        if dato.get("error"):
            raise RuntimeError(f"Ollama: {dato['error']}")

        respuesta = str(dato.get("response") or "").strip()
        termino = dato.get("done") is True
        if not termino or not respuesta:
            motivo = dato.get("done_reason", "no informado")
            pensamiento = len(str(dato.get("thinking") or ""))
            tokens = dato.get("eval_count", "no informado")
            print(
                "[OLLAMA:SINTESIS] respuesta incompleta: "
                f"done={dato.get('done')!r}; motivo={motivo}; "
                f"texto_final={len(respuesta)} caracteres; "
                f"thinking={pensamiento} caracteres; eval_count={tokens}"
            )
            if not termino:
                raise RuntimeError(
                    f"generación incompleta (done={dato.get('done')!r}, motivo={motivo})"
                )
            raise RuntimeError(
                f"Ollama finalizó sin texto final (motivo={motivo}, "
                f"thinking={pensamiento} caracteres)"
            )

        print(
            f"[OLLAMA:SINTESIS] respuesta completa ({len(respuesta)} caracteres); "
            f"motivo={dato.get('done_reason', 'no informado')}; "
            f"tokens={dato.get('eval_count', 'no informado')}"
        )
    except Exception as error:
        print(f"[SINTESIS] Ollama no pudo completar la respuesta: {error}")
        yield _respaldo(resultados, str(error))
        return
    finally:
        if response is not None:
            response.close()

    if error_router:
        print("[ROUTER] Se usaron categorías de respaldo locales.")
    if fuentes:
        respuesta += "\n\nFuentes: " + ", ".join(fuentes)
    # Se emite al final: si el stream de Ollama se corta no se muestra media respuesta.
    yield respuesta
