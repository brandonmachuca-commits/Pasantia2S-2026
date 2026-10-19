"""Coordinador RAG para documentos dinámicos en backend/Documentos."""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Optional

from agent import (
    Agent,
    STATIC_CATEGORY_ALIASES,
    STATIC_FALLBACK_CATEGORIES,
    SUPPORTED_EXTENSIONS,
)
from agentes import AGENTES, responder_stream


def quitar_acentos(texto: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(character) != "Mn"
    )


def normalizar_consulta(consulta: str) -> str:
    """Conserva el texto del estudiante y normaliza espacios."""
    return re.sub(r"\s+", " ", quitar_acentos(consulta)).strip()


def _ruta_documentos() -> Path:
    backend_root = Path(__file__).resolve().parent
    configured = os.getenv("DOCUMENTOS_DIR", "").strip()
    if not configured:
        return (backend_root / "Documentos").resolve()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = backend_root / path
    return path.resolve()


class RAGSystem:
    """Memoria de conversación, agentes por carpeta y recarga sin reiniciar.

    Cada carpeta inmediata de Documentos se convierte en una categoría. Los
    archivos que contenga se leen recursivamente por su Agent.
    """

    SESSION_TTL_SECONDS = max(60, int(os.getenv("RAG_SESSION_TTL_SECONDS", "3600")))

    def __init__(self, documents_root: Optional[str | Path] = None):
        self.documents_root = Path(documents_root or _ruta_documentos()).resolve()
        self.documents_root.mkdir(parents=True, exist_ok=True)
        self.static_root = (Path(__file__).resolve().parent / "data" / "processed").resolve()
        self.model = self._load_model()
        self.agentes: dict[str, Agent] = {}
        self.sessions: dict[str, dict] = {}
        self.last_topic: Optional[str] = None
        self._reload_lock = threading.RLock()
        self._loaded_signatures: dict[str, tuple] = {}
        self._last_document_scan = 0.0
        self._auto_reload = os.getenv("RAG_AUTO_RELOAD_DOCUMENTS", "1").strip() != "0"
        self._scan_interval = max(1.0, float(os.getenv("RAG_DOCUMENT_SCAN_INTERVAL_SECONDS", "2")))
        self.reload_category()
        print(f"[RAG] Sistema dinámico inicializado desde {self.documents_root}")

    @staticmethod
    def _load_model():
        """Carga embeddings locales si están instalados; la búsqueda textual es el respaldo."""
        if os.getenv("RAG_ENABLE_EMBEDDINGS", "1").strip() == "0":
            print("[RAG] Embeddings desactivados por configuración; uso búsqueda textual")
            return None
        try:
            from sentence_transformers import SentenceTransformer

            model_name = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            model = SentenceTransformer(model_name)
            print(f"[RAG] Embeddings locales cargados: {model_name}")
            return model
        except Exception as error:
            print(f"[RAG] Embeddings no disponibles; uso búsqueda textual: {error}")
            return None

    def _dynamic_category_directories(self) -> dict[str, Path]:
        if not self.documents_root.is_dir():
            return {}
        return {
            path.name: path
            for path in self.documents_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }

    def _available_categories(self) -> list[str]:
        """Categorías dinámicas más las categorías estáticas permitidas."""
        dynamic = self._dynamic_category_directories()
        names = set(dynamic)
        if self.static_root.is_dir():
            names.update(
                path.name
                for path in self.static_root.iterdir()
                if path.is_dir()
                and path.name.casefold() in STATIC_FALLBACK_CATEGORIES
                and not path.name.startswith(".")
            )

        # Evita presentar dos agentes para la misma colección de materias.
        # Si existe la versión dinámica bajo uno de los dos nombres, ese agente
        # ya sabe buscar también el alias estático correspondiente.
        if "materias" in {name.casefold() for name in dynamic} and "cursos" not in {name.casefold() for name in dynamic}:
            names = {name for name in names if name.casefold() != "cursos"}
        if "cursos" in {name.casefold() for name in dynamic} and "materias" not in {name.casefold() for name in dynamic}:
            names = {name for name in names if name.casefold() != "materias"}
        return sorted(names, key=str.casefold)

    def _make_agent(self, category: str) -> Agent:
        return Agent(
            nombre=category,
            carpeta=category,
            model=self.model,
            documents_root=self.documents_root,
            static_root=self.static_root,
        )

    def _status_data(self) -> dict:
        return {
            "ruta_documentos": str(self.documents_root),
            "categorias": {
                category: agent.status()
                for category, agent in sorted(self.agentes.items(), key=lambda item: item[0].casefold())
            },
        }

    def status(self) -> dict:
        self._refresh_documents()
        return self._status_data()

    def _document_snapshot(self) -> dict[str, tuple]:
        snapshot = {}
        dynamic_directories = self._dynamic_category_directories()
        for category in self._available_categories():
            items = []
            roots: list[tuple[str, Path]] = []
            dynamic_dir = next(
                (path for name, path in dynamic_directories.items() if name.casefold() == category.casefold()),
                None,
            )
            if dynamic_dir is not None:
                roots.append(("Documentos", dynamic_dir))
            if category.casefold() in STATIC_FALLBACK_CATEGORIES:
                static_names = STATIC_CATEGORY_ALIASES.get(category.casefold(), (category,))
                roots.extend(
                    ("data/processed", self.static_root / name)
                    for name in static_names
                    if (self.static_root / name).is_dir()
                )
            for label, root in roots:
                for path in root.rglob("*"):
                    if (
                        not path.is_file()
                        or path.suffix.casefold() not in SUPPORTED_EXTENSIONS
                        or path.name.startswith(("~$", "."))
                        or path.name.casefold().endswith((".tmp", ".part"))
                    ):
                        continue
                    try:
                        stat = path.stat()
                        relative = f"{label}/{root.name}/{path.relative_to(root).as_posix()}"
                        items.append((relative, stat.st_size, stat.st_mtime_ns))
                    except OSError:
                        continue
            snapshot[category] = tuple(sorted(items))
        return snapshot

    def _refresh_documents(self) -> None:
        """Detecta archivos/categorías agregados, modificados o quitados."""
        if not self._auto_reload:
            return
        now = time.monotonic()
        if now - self._last_document_scan < self._scan_interval:
            return
        with self._reload_lock:
            now = time.monotonic()
            if now - self._last_document_scan < self._scan_interval:
                return
            current = self._document_snapshot()
            previous = self._loaded_signatures
            if current != previous:
                removed = set(previous) - set(current)
                for name in removed:
                    self.agentes.pop(name, None)
                for name, signature in current.items():
                    if previous.get(name) == signature:
                        continue
                    agent = self.agentes.get(name)
                    if agent is None:
                        self.agentes[name] = self._make_agent(name)
                    else:
                        agent.load()
                self._loaded_signatures = current
                self._rebuild_entity_index()
                print("[RAG] Cambios en Documentos detectados; índices actualizados")
            self._last_document_scan = time.monotonic()

    def limpiar_sesiones(self) -> None:
        now = time.time()
        for session_id in list(self.sessions):
            state = self.sessions[session_id]
            if now - state.get("last_seen", now) > self.SESSION_TTL_SECONDS:
                del self.sessions[session_id]

    def reset_memory(self, session_id: Optional[str] = None) -> None:
        if session_id:
            self.sessions.pop(session_id, None)
        else:
            self.sessions.clear()

    def reload_category(self, categoria: Optional[str] = None) -> dict:
        """Recarga una carpeta o reescanea todas, incluyendo nuevas categorías."""
        with self._reload_lock:
            categories = self._available_categories()
            if categoria is None or str(categoria).strip().casefold() in {"", "all", "todos"}:
                current_names = set(categories)
                for existing in list(self.agentes):
                    if existing not in current_names:
                        del self.agentes[existing]
                for name in categories:
                    agent = self.agentes.get(name)
                    if agent is None:
                        self.agentes[name] = self._make_agent(name)
                    else:
                        agent.load()
                self._loaded_signatures = self._document_snapshot()
            else:
                requested = str(categoria).strip()
                actual_name = next(
                    (name for name in categories if name.casefold() == requested.casefold()),
                    None,
                )
                if actual_name is None:
                    print(f"[RAG] No existe la categoría dinámica ni estática '{requested}'")
                    existing = next((name for name in self.agentes if name.casefold() == requested.casefold()), None)
                    if existing:
                        del self.agentes[existing]
                    self._loaded_signatures.pop(existing or requested, None)
                    self._rebuild_entity_index()
                    return self._status_data()
                agent = self.agentes.get(actual_name)
                if agent is None:
                    self.agentes[actual_name] = self._make_agent(actual_name)
                else:
                    agent.load()
                current = self._document_snapshot()
                if actual_name in current:
                    self._loaded_signatures[actual_name] = current[actual_name]

            self._rebuild_entity_index()
            self._last_document_scan = time.monotonic()
            return self._status_data()

    def _rebuild_entity_index(self) -> None:
        """Construye alias de materias solo desde fuentes confiables de los documentos."""
        aliases: dict[str, str] = {}
        stop = {"de", "la", "el", "en", "y", "los", "las", "un", "una", "del", "al", "si", "no", "se", "que", "con", "por", "para"}

        def add(alias: str, code: str) -> None:
            alias = re.sub(r"\s+", " ", str(alias)).strip(" .,:;-–")
            key = quitar_acentos(alias).casefold()
            if len(key) >= 2 and key not in stop:
                aliases[key] = code

        legend = re.compile(r"^(?P<head>[^\n]{3,90}?)\s+[–—-]\s+(?P<who>[A-ZÁÉÍÓÚÑ][^\n–—]{3,80})$", re.MULTILINE)
        scheduled = re.compile(
            r"^(?P<code>[^\n:(]{2,14}?)(?: \([^)]*\))?: (?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado)\b",
            re.MULTILINE,
        )
        for agent in self.agentes.values():
            for chunk, source in zip(agent.chunks, agent.chunk_sources):
                # Cada carpeta de cursos/<Código>/ es una materia; "TIP - <Nombre>" es su nombre oficial.
                folder = re.search(r"/(?:cursos|materias)/([^/]+)/", source)
                if folder and len(folder.group(1)) <= 30:
                    code = folder.group(1).strip()
                    add(code, code)
                    title = re.match(r"\s*TIP - ([^\n]+?)(?:\s+Search this site|\n|$)", chunk)
                    if title:
                        add(title.group(1), code)

                if source.startswith("Documentos/"):
                    # Leyenda de horarios: "Arq Arquitectura de Computadoras – Jesús Guibert".
                    for match in legend.finditer(chunk):
                        tokens = match.group("head").split()
                        if len(tokens) < 2:
                            continue
                        size = 2 if len(tokens) > 3 and tokens[2].casefold() == "taller" else 1
                        code = " ".join(tokens[:size])
                        add(code, code)
                        add(" ".join(tokens[size:]), code)
                    # Tablas de horarios y parciales: "PyE (4er. Semestre): Lunes 22 ...".
                    for match in scheduled.finditer(chunk):
                        code = match.group("code").strip()
                        add(code, code)

                for line in chunk.splitlines():
                    match = re.search(r"\bDicta(?:n)?\s*:\s*(.+)", line, flags=re.IGNORECASE)
                    if not match:
                        continue
                    for segment in match.group(1).split(","):
                        course = re.match(
                            r"\s*([A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{0,9})"
                            r"(?:\s*\(([^)]{3,100})\))?",
                            segment,
                        )
                        if course:
                            code = course.group(1).strip()
                            add(code, code)
                            if course.group(2):
                                add(course.group(2), code)

        # Un alias genérico que es el comienzo del nombre de otra materia ("matemática"
        # frente a "matemática discreta y lógica 1") es ambiguo: se descarta.
        for key in list(aliases):
            if any(other != key and other.startswith(key + " ") and aliases[other] != aliases[key] for other in aliases):
                del aliases[key]

        self._entity_aliases = sorted(
            aliases.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def detectar_materias(self, pregunta: str) -> list[str]:
        """Todas las materias nombradas; el texto ya reconocido no se vuelve a usar."""
        query = quitar_acentos(pregunta).casefold()
        found: list[str] = []
        for alias, canonical in getattr(self, "_entity_aliases", []):
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            if re.search(pattern, query):
                if canonical not in found:
                    found.append(canonical)
                query = re.sub(pattern, " ", query)
        return found

    def aliases_de(self, codes: list[str]) -> list[str]:
        wanted = set(codes)
        return [alias for alias, canonical in getattr(self, "_entity_aliases", []) if canonical in wanted]

    def detectar_materia(self, pregunta: str) -> Optional[str]:
        found = self.detectar_materias(pregunta)
        return found[0] if found else None

    @staticmethod
    def _es_saludo(pregunta: str) -> bool:
        q = quitar_acentos(pregunta.casefold()).strip(" ¿?¡!.,")
        return q in {
            "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
            "que tal", "como estas",
        }

    @staticmethod
    def _es_seguimiento(pregunta: str) -> bool:
        q = quitar_acentos(pregunta.casefold()).strip()
        words = q.split()
        if len(words) > 12:
            return False
        starts_as_followup = q.startswith(("y ", "¿y ", "tambien ", "ademas "))
        refers_to_previous = any(term in q for term in (
            "su ", "sus ", "esa ", "ese ", "la misma", "el mismo", "cuando es",
            "cuando son", "y el examen", "y los parciales", "y la fecha",
        ))
        return starts_as_followup or refers_to_previous

    @staticmethod
    def _nombra_otro_tema(pregunta: str) -> bool:
        """"y el de Física?" nombra algo nuevo aunque no sea una materia conocida."""
        q = quitar_acentos(pregunta.casefold())
        return bool(re.search(
            r"\b(?:de|del)\s+(?!la\b|el\b|lo\b|los\b|las\b|esa\b|ese\b|eso\b|esta\b|este\b|ahi\b|alli\b)\w{2,}",
            q,
        ))

    @staticmethod
    def _topic_hint(pregunta: str) -> str:
        q = quitar_acentos(pregunta.casefold())
        labels = (
            ("horarios", ("horario", "horarios", "presencial", "dias de clase", "a que hora")),
            ("docentes", ("profesor", "profesora", "docente", "profe")),
            ("parciales y exámenes", ("parcial", "examen", "evaluacion", "prueba")),
            ("materias", ("materia", "asignatura", "programa", "temario")),
            ("ingreso", ("ingresar", "ingreso")),
            ("egreso", ("egresar", "egreso")),
        )
        return ", ".join(
            label for label, terms in labels if any(term in q for term in terms)
        )

    def _contextualizar(self, pregunta: str, state: dict) -> str:
        current_entity = self.detectar_materia(pregunta)
        if current_entity:
            state["last_entity"] = current_entity
        if self._es_seguimiento(pregunta):
            context = ""
            # La materia anterior solo se hereda si la pregunta no nombra otra.
            if (
                not current_entity
                and state.get("last_entity")
                and not self._nombra_otro_tema(pregunta)
            ):
                context += f" La consulta se refiere a {state['last_entity']}."
            # "¿Y el de PyE?" conserva lo que se estaba preguntando (docentes, parciales…).
            if not self._topic_hint(pregunta) and state.get("last_topic"):
                context += f" El tema anterior era: {state['last_topic']}."
            pregunta = pregunta.rstrip() + context

        topic = self._topic_hint(pregunta)
        if topic:
            state["last_topic"] = topic
            self.last_topic = topic
        state["last_seen"] = time.time()
        return pregunta

    async def answer_stream(self, question: str, session_id: str, client=None):
        """Interfaz SSE compatible con main.py; ejecuta Ollama fuera del event loop."""
        if not question or not question.strip():
            yield ("Escribí una pregunta para poder ayudarte.", "system")
            return
        if self._es_saludo(question):
            yield (
                "¡Hola! Soy el asistente de la carrera Tecnólogo en Informática. "
                "¿En qué puedo ayudarte?",
                "system",
            )
            return

        await asyncio.to_thread(self._refresh_documents)

        sid = session_id or "anonimo"
        state = self.sessions.setdefault(
            sid,
            {"last_topic": None, "last_entity": None, "last_seen": time.time(), "historial": []},
        )
        self.limpiar_sesiones()
        query = self._contextualizar(normalizar_consulta(question.strip()), state)
        print(f"[RAG:MEMORIA] sesión={sid} | consulta contextualizada={query}", flush=True)

        historial = list(state.get("historial", []))

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        texto_completo: list[str] = []

        materias = self.detectar_materias(query)
        preferidas = self.aliases_de(materias)
        equivalencias = [self.aliases_de([codigo]) for codigo in materias]

        def produce() -> None:
            try:
                for response_part in responder_stream(
                    query, self.agentes, historial=historial,
                    materia_preferida=preferidas or None, equivalencias=equivalencias,
                ):
                    texto_completo.append(response_part)
                    loop.call_soon_threadsafe(queue.put_nowait, (response_part, "document"))
            except Exception as error:
                message = f"No pude procesar la consulta. {type(error).__name__}: {error}"
                loop.call_soon_threadsafe(queue.put_nowait, (message, "error"))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        threading.Thread(target=produce, daemon=True, name="rag-respuesta").start()
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item

        respuesta_final = "".join(texto_completo).strip()
        if respuesta_final:
            state.setdefault("historial", []).append({"pregunta": question.strip(), "respuesta": respuesta_final})
            state["historial"] = state["historial"][-5:]

    def answer(self, question: str, session_id: str = "anonimo") -> str:
        """Interfaz síncrona útil para consola, scripts o integraciones antiguas."""
        self._refresh_documents()
        state = self.sessions.setdefault(
            session_id,
            {"last_topic": None, "last_entity": None, "last_seen": time.time()},
        )
        query = self._contextualizar(normalizar_consulta(question.strip()), state)
        print(f"[RAG:MEMORIA] sesión={session_id} | consulta contextualizada={query}", flush=True)
        materias = self.detectar_materias(query)
        return "".join(responder_stream(
            query, self.agentes, materia_preferida=self.aliases_de(materias) or None,
            equivalencias=[self.aliases_de([codigo]) for codigo in materias],
        ))

