import asyncio
import threading
from typing import Optional
from agent import Agent
from agentes import AGENTES, responder_stream
import re
import unicodedata
from pathlib import Path
import time

MATERIAS = {
    # primer semestre
   "PP": {
        "oficial": "Principios de Programación",
        "aliases": [
            "PP",
            "Principios de Programación",
            "Principios de Programacion",
            "principios de programacion"
        ]
    },

    "MDL1": {
        "oficial": "Matemática Discreta y Lógica 1",
        "aliases": [
            "MDL1",
            "Matemática Discreta y Lógica 1",
            "Matematica Discreta y Logica 1",
            "mdl1",
            "discreta 1"
        ]
    },

    "Arq": {
        "oficial": "Arquitectura del Computador",
        "aliases": [
            "ARQ",
            "Arquitectura del Computador",
            "arquitectura",
            "arq"
        ]
    },

    "I1": {
        "oficial": "Inglés Técnico 1",
        "aliases": [
            "I1",
            "Inglés Técnico 1",
            "Ingles Tecnico 1",
            "ingles 1"
        ]
    },

    "MN": {
        "oficial": "Matemática Nivelación",
        "aliases": [
            "MN",
            "Matemática Nivelación",
            "Matematica Nivelacion",
            "mn",
            "nivelacion"
        ]
    },
    # segundo semestre

  "BD1": {
        "oficial": "Bases de Datos 1",
        "aliases": [
            "BD1",
            "Bases de Datos 1",
            "bd1",
            "bases",
            "BD"
        ]
    },

    "I2": {
        "oficial": "Inglés Técnico 2",
        "aliases": [
            "I2",
            "Inglés Técnico 2",
            "Ingles Tecnico 2",
            "ingles 2",
            "I2"
        ]
    },

    "EDA": {
        "oficial": "Estructuras de Datos y Algoritmos",
        "aliases": [
            "EDA",
            "Estructuras de Datos y Algoritmos",
            "Estructuras de Datos y Algoritmos",
            "eda"
        ]
    },

    "MDL2": {
        "oficial": "Matemática Discreta y Lógica 2",
        "aliases": [
            "MDL2",
            "Matemática Discreta y Lógica 2",
            "Matematica Discreta y Logica 2",
            "mdl2",
            "discreta 2"
        ]
    },

    "SO": {
        "oficial": "Sistemas Operativos",
        "aliases": [
            "SO",
            "Sistemas Operativos"
        ]
    },

    # 3er Semestre

  "BD2": {
        "oficial": "Bases de Datos 2",
        "aliases": [
            "BD2",
            "Bases de Datos 2",
            "bases 2",
            "bd2"
        ]
    },

    "COE": {
        "oficial": "Comunicación Oral y Escrita",
        "aliases": [
            "COE",
            "Comunicación Oral y Escrita",
            "Comunicacion Oral y Escrita",
            "coe"
        ]
    },

    "Contab": {
        "oficial": "Contabilidad",
        "aliases": [
            "Contab",
            "Contabilidad",
            "contab"
        ]
    },

    "Redes": {
        "oficial": "Redes de Computadoras",
        "aliases": [
            "Redes",
            "Redes de Computadoras",
            "redes"
        ]
    },

    "ProgAvanz": {
        "oficial": "Programación Avanzada",
        "aliases": [
            "ProgAvanz",
            "Prog Avanz",
            "Programación Avanzada",
            "Programacion Avanzada",
            "PA"
        ]
    },

    # 4to Semestre

    "Adm Inf1": {
        "oficial": "Administración de Infraestructuras",
        "aliases": [
            "Adm Inf1",
            "infra 1",
            "Administración de Infraestructuras",
            "Administracion de Infraestructuras",
            "admininfra"
        ]
    },

    "IngSoft": {
        "oficial": "Ingeniería de Software",
        "aliases": [
            "Ing Soft",
            "IngSoft",
            "ISoft",
            "ingenieria",
            "Ingeniería",
            "Ingenieria de Software",
            "Ingeniería de Software"
        ]
    },

    "PyE": {
        "oficial": "Probabilidad y Estadística",
        "aliases": [
            "PyE",
            "probabilidad",
            "estadistica",
            "Probabilidad y Estadistica",
            "Probabilidad y Estadística",
            "pye"
        ]
    },

    "ProgAplic": {
        "oficial": "Programación de Aplicaciones",
        "aliases": [
            "ProgAplic",
            "Programacion de Aplicaciones",
            "Programación de Aplicaciones",
            "PApl"
        ]
    },

    "RPyL": {
        "oficial": "Relaciones Personales y Laborales",
        "aliases": [
            "RPyL",
            "Relaciones Personales y Laborales",
            "Relaciones Personales y Laborales",
            "rpyl"
        ]
    },

    # 5to Semestre

    "Internet Ricas": {
        "oficial": "Taller de Aplicaciones de Internet Ricas",
        "aliases": [
            "RIA",
            "Internet Ricas",
            "Taller de Aplicaciones de Internet Ricas",
            "ricas",
            "Ricas",
            "intricas"
        ]
    },

     "JAVA EE": {
        "oficial": "Taller de Sistemas de Información Java EE",
        "aliases": [
            "JAVA EE",
            "JAVAEE",
            "Java",
            "Java EE",
            "Taller de Sistemas de Información Java EE",
            "java"
        ]
    },

    "ADMINF II": {
        "oficial": "Administración de Infraestructuras 2",
        "aliases": [
            "ADMINFII",
            "infra 2",
            "Administración de Infraestructuras 2",
            "Administracion de Infraestructuras 2",
            "admin infra 2",
            "admininfra2"
        ]
    },

    "Pasantia": {
        "oficial": "Pasantia Laboral",
        "aliases": [
            "Pasantia",
            "pasantia",
            "Pasantia Laboral",
            "Pasantia Laboral"
        ]
    },
    "PHP": {
        "oficial": "Taller de Desarrollo de Aplicaciones Web con PHP",
        "aliases": [
            "PHP",
            "Taller de Desarrollo de Aplicaciones Web con PHP",
            "php"
        ]
    },

    "Móviles": {
        "oficial": "Taller de Desarrollo de Aplicaciones Para Dispositivos Móviles",
        "aliases": [
            "Móviles",
            "moviles",
            "android",
            "Taller de Desarrollo de Aplicaciones Para Dispositivos Móviles"
        ]
    },
    
    # 6to Semestre

    "JyM": {
        "oficial": "Sistemas de Gestión de Contenidos",
        "aliases": [
            "JyM",
            "jym",
            "Sistemas de Gestión de Contenidos",
            "Sistemas de Gestion de Contenidos"
        ]
    },

    ".NET": {
        "oficial": "Taller de Sistemas de Información .NET",
        "aliases": [
            ".NET",
            "dotnet",
            "Taller de Sistemas de Información .NET",
            "Taller de Sistemas de Informacion .NET"
        ]
    },

    "Control": {
        "oficial": "Introducción a los Sistemas de Control",
        "aliases": [
            "Control",
            "control",
            "Introducción a los Sistemas de Control",
            "Introduccion a los Sistemas de Control"
        ]
    },

    "Proyecto": {
        "oficial": "Proyecto",
        "aliases": [
            "Proyecto",
            "proyecto"
        ]
    },

    "Innovacion": {
        "oficial": "Taller de Gestión de la Innovación en Tecnologías",
        "aliases": [
            "Innovación",
            "innovacion",
            "Taller de Gestión de la Innovación en Tecnologías",
            "Taller de Gestion de la Innovacion en Tecnologias"
        ]
    },

    "Juegos": {
        "oficial": "Introducción al Desarrollo de Juegos",
        "aliases": [
            "Juegos",
            "juegos",
            "Introducción al Desarrollo de Juegos",
            "Introduccion al Desarrollo de Juegos"
        ]
    },

 
}


def quitar_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

def normalizar_consulta(consulta: str) -> str:

    consulta = quitar_acentos(consulta.lower())

    for sigla, datos in MATERIAS.items():

        aliases = [datos["oficial"]] + datos["aliases"]

        aliases = sorted(
            aliases,
            key=len,
            reverse=True
        )

        for alias in aliases:

            alias = quitar_acentos(alias.lower())

            consulta = re.sub(
                rf"\b{re.escape(alias)}\b",
                sigla,
                consulta,
                flags=re.IGNORECASE
            )

    return consulta



class RAGSystem:
    """Adaptador del backend: memoria, agentes y streaming compatible con main.py."""

    def __init__(self):
        self.model = self._load_model()
        self.agentes = {
            nombre: Agent(nombre, nombre, self.model if nombre == "cursos" else None)
            for nombre in AGENTES
        }
        self.sessions = {}
        self.last_topic = None
        print("[RAG] Sistema multiagente con Ollama inicializado")

    def _load_model(self):
        """Modelo local de embeddings para búsqueda de programas; Ollama redacta."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[RAG] Embeddings locales cargados")
            return model
        except Exception as error:
            print(f"[RAG] Embeddings no disponibles; cursos usará búsqueda por texto: {error}")
            return None

    def limpiar_sesiones(self):
        ahora = time.time()
        for sid in list(self.sessions):
            if ahora - self.sessions[sid]["last_seen"] > 3600:
                del self.sessions[sid]
        self.last_topic = next(
            (m["last_topic"] for m in reversed(list(self.sessions.values())) if m.get("last_topic")),
            None,
        )

    def reset_memory(self):
        self.sessions.clear()
        self.last_topic = None

    def reload_category(self, categoria: Optional[str] = None):
        alias = {
            "calendario": "info_general",
            "presencialidades": "cursos",
        }
        objetivo = alias.get(categoria, categoria) if categoria else None
        if objetivo and objetivo in self.agentes:
            self.agentes[objetivo].load()
        elif objetivo is None:
            for agente in self.agentes.values():
                agente.load()

    def detectar_materia(self, pregunta: str) -> Optional[str]:
        pregunta_norm = quitar_acentos(pregunta).casefold()
        for sigla, datos in MATERIAS.items():
            aliases = [datos["oficial"], *datos["aliases"]]
            for alias in sorted(aliases, key=len, reverse=True):
                alias_norm = quitar_acentos(alias).casefold()
                if re.search(rf"\b{re.escape(alias_norm)}\b", pregunta_norm):
                    return sigla
        return None

    @staticmethod
    def _es_saludo(pregunta: str) -> bool:
        q = quitar_acentos(pregunta.casefold()).strip()
        return q in {
            "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
            "que tal", "como estas",
        }

    async def answer_stream(self, question: str, session_id: str, client=None):
        """Entrega tokens al endpoint SSE sin bloquear el event loop de FastAPI."""
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

        sid = session_id or "anonimo"
        memory = self.sessions.setdefault(
            sid, {"last_topic": None, "last_entity": None, "last_seen": time.time()}
        )
        memory["last_seen"] = time.time()
        self.limpiar_sesiones()

        pregunta = normalizar_consulta(question.strip())
        materia = self.detectar_materia(pregunta)
        if materia:
            memory["last_entity"] = materia
        elif memory.get("last_entity") and re.search(
            r"\b(su|sus|esa|ese|esa materia|la misma)\b", quitar_acentos(pregunta.casefold())
        ):
            # Resuelve seguimientos breves conservando la materia de la sesión.
            pregunta = re.sub(
                r"\b(su|sus|esa materia|esa|ese|la misma)\b",
                memory["last_entity"],
                pregunta,
                flags=re.IGNORECASE,
            )
            materia = memory["last_entity"]

        materia_aliases = None
        if materia and materia in MATERIAS:
            datos = MATERIAS[materia]
            materia_aliases = [
                materia,
                datos.get("oficial", ""),
                *datos.get("aliases", []),
            ]

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def producir():
            try:
                for fragmento in responder_stream(
                    pregunta, self.agentes, materia_aliases=materia_aliases
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, (fragmento, "document"))
            except Exception as error:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    (f"No pude procesar la consulta: {type(error).__name__}: {error}", "error"),
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        threading.Thread(target=producir, daemon=True, name="respuesta-ollama").start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
