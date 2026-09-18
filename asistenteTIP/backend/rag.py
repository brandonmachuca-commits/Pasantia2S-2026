import json
import requests
from typing import Optional
from datetime import datetime
from agent import Agent
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
            "Principios de Programacion"
        ]
    },

    "MDL1": {
        "oficial": "Matemática Discreta y Lógica 1",
        "aliases": [
            "MDL1",
            "Matemática Discreta y Lógica 1",
            "Matematica Discreta y Logica 1"
        ]
    },

    "Arq": {
        "oficial": "Arquitectura del Computador",
        "aliases": [
            "ARQ",
            "Arquitectura del Computador",
        ]
    },

    "I1": {
        "oficial": "Inglés Técnico 1",
        "aliases": [
            "I1",
            "Inglés Técnico 1",
            "Ingles Tecnico 1"
        ]
    },

    "MN": {
        "oficial": "Matemática Nivelación",
        "aliases": [
            "MN",
            "Matemática Nivelación",
            "Matematica Nivelacion"
        ]
    },
    # segundo semestre

  "BD1": {
        "oficial": "Bases de Datos 1",
        "aliases": [
            "BD1",
            "Bases de Datos 1",
        ]
    },

    "I2": {
        "oficial": "Inglés Técnico 2",
        "aliases": [
            "I2",
            "Inglés Técnico 2",
            "Ingles Tecnico 2"
        ]
    },

    "EDA": {
        "oficial": "Estructuras de Datos y Algoritmos",
        "aliases": [
            "EDA",
            "Estructuras de Datos y Algoritmos",
            "Estructuras de Datos y Algoritmos"
        ]
    },

    "MDL2": {
        "oficial": "Matemática Discreta y Lógica 2",
        "aliases": [
            "MDL2",
            "Matemática Discreta y Lógica 2",
            "Matematica Discreta y Logica 2"
        ]
    },

    "SO": {
        "oficial": "Sistemas Operativos",
        "aliases": [
            "SO",
            "Sistemas Operativos",
        ]
    },

    # 3er Semestre

  "BD2": {
        "oficial": "Bases de Datos 2",
        "aliases": [
            "BD2",
            "Bases de Datos 2",
        ]
    },

    "COE": {
        "oficial": "Comunicación Oral y Escrita",
        "aliases": [
            "COE",
            "Comunicación Oral y Escrita",
            "Comunicacion Oral y Escrita"
        ]
    },

    "Contab": {
        "oficial": "Contabilidad",
        "aliases": [
            "Contab",
            "Contabilidad"
        ]
    },

    "Redes": {
        "oficial": "Redes de Computadoras",
        "aliases": [
            "Redes",
            "Redes de Computadoras",
        ]
    },

    "ProgAvanz": {
        "oficial": "Programación Avanzada",
        "aliases": [
            "ProgAvanz",
            "Prog Avanz",
            "Programación Avanzada",
            "Programacion Avanzada",
        ]
    },

    # 4to Semestre

    "Adm Inf1": {
        "oficial": "Administración de Infraestructuras",
        "aliases": [
            "Adm Inf1",
            "infra 1",
            "Administración de Infraestructuras",
            "Administracion de Infraestructuras"
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
            "Probabilidad y Estadística"
        ]
    },

    "ProgAplic": {
        "oficial": "Programación de Aplicaciones",
        "aliases": [
            "ProgAplic",
            "Programacion de Aplicaciones",
            "Programación de Aplicaciones"
        ]
    },

    "RPyL": {
        "oficial": "Relaciones Personales y Laborales",
        "aliases": [
            "RPyL",
            "Relaciones Personales y Laborales",
            "Relaciones Personales y Laborales"
        ]
    },

    # 5to Semestre

    "Internet Ricas": {
        "oficial": "Taller de Aplicaciones de Internet Ricas",
        "aliases": [
            "RIA",
            "Internet Ricas",
            "Taller de Aplicaciones de Internet Ricas"
        ]
    },

     "JAVA EE": {
        "oficial": "Taller de Sistemas de Información Java EE",
        "aliases": [
            "JAVA EE",
            "JAVAEE",
            "Java",
            "Java EE",
            "Taller de Sistemas de Información Java EE"
        ]
    },

    "ADMINF II": {
        "oficial": "Administración de Infraestructuras 2",
        "aliases": [
            "ADMINFII",
            "infra 2",
            "Administración de Infraestructuras 2",
            "Administracion de Infraestructuras 2"
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
            "Taller de Desarrollo de Aplicaciones Web con PHP"
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
            "Sistemas de Gestión de Contenidos"
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

    AGENTES = {
        "presencialidades": [
            "presencial",
            "presencialidad",
            "asistencia",
            "que dias",
            "que día",
            "dias tiene",
            "cuando hay clase",
            "dias hay"
        ],
        
        "calendario": [
            "calendario",
            "fecha",
            "inicio",
            "fin",
            "feriado",
            "termina",
            "empieza",
            "examen",
            "examenes",
            "cuando termina",
            "cuando terminan",
            "cuando empieza",
            "cuando empiezan",
            "cuando comienzan",
            "cuando comienza",
            "carnaval",
            "feriados",
            "navidad",
            "trabajador",
            "independencia",
            "18 de julio",
            "25 de agosto",
            "1 de mayo",
            "turismo",
            "artigas"
            
        ],
        "horarios": [
            "horario",
            "hora",
            "a que hora",
            "que horario",
            "cuando se dicta",
            "cuando es",
            "que dia",
            "que dias",
            "materias hoy",
            "cursada"
            ],

        "parciales": [
            "parcial",
            "parciales",
            "evaluacion",
            "prueba"
        ],

        "cursos": [
            "materia",
            "materias",
            "curso",
            "cursos",
            "asignatura",
            "asignaturas",
            "que se estudia",
            "programa",
            "semestre",
            "previa",
            "previas",
            "previaturas",
            "previatura"
        ],
        "docentes": [
            "docente",
            "profesor",
            "profesora",
            "quien dicta"
            ]
    }

  
    def __init__(self):

        self.model = self._load_model()

        # memoria conversacional simple
        self.last_topic: Optional[str] = None
        self.last_entity: Optional[str] = None

        # cargar el contexto fijo
        #self.contexto_fijo = self._cargar_contexto_fijo()

        self.contextos_materias = self._cargar_contextos_materias()
        self.contextos_presencialidades = self._cargar_contextos_presencialidades()

        self.contexto_cursos = self._cargar_contexto_cursos()

        self.contextos = {}

        for nombre in [
            "calendario",
            "horarios",
            "parciales",
            "docentes",
            "presencialidades"
        ]:
            self.contextos[nombre] = self.cargar_contexto_fijo(nombre)

        # solo agente de cursos 
        self.agentes = {
            "cursos": Agent(
                "cursos",
                "cursos",
                self.model
            )
        }

        self.sessions = {}



        print("[RAG] Sistema inicializado")

    #

    def _cargar_contexto_cursos(self):
        archivo = (
            Path(__file__).resolve().parent
            / "data"
            / "processed"
            / "cursos"
            / "contenido.txt"
        )

        return archivo.read_text(encoding="utf-8")

    def cargar_contexto_fijo(self, agente):
        BASE_DIR = Path(__file__).resolve().parent

        archivo = (
            BASE_DIR
            / "data"
            / "processed"
            / agente
            / "contenido.txt"
        )

        if archivo.exists():
            return archivo.read_text(encoding="utf-8")
        else:
            return f"No se encontro el contenido para {agente}"
        


    # def detectar_agente(self, pregunta: str):
    #     pregunta = quitar_acentos(pregunta.lower())

    #     if any(x in pregunta for x in ["docente", "profesor", "profesora", "quien dicta"]):
    #         return "docentes"

    #     if any(x in pregunta for x in ["horario", "hora", "a que hora"]):
    #         return "horarios"

    #     if any(x in pregunta for x in ["parcial", "parciales"]):
    #         return "parciales"

    #     if any(x in pregunta for x in ["presencial", "presencialidad"]):
    #         return "presencialidades"

    #     if any(x in pregunta for x in ["calendario", "feriado", "examen"]):
    #         return "calendario"

    #     if any(x in pregunta for x in ["apoyo", "beca", "bienestar"]):
    #         return "apoyo"

    #     return None

    # def _cargar_contexto_fijo(self) -> str:
    #     BASE_DIR = Path(__file__).resolve().parent
        
    #     agentes_chicos = [
    #         "calendario",
    #         "horarios",
    #         "parciales",
    #         "docentes",
    #         "presencialidades",
    #         "apoyo"
    #     ]

    #     partes = []

    #     for agente in agentes_chicos:

    #         archivo = (
    #             BASE_DIR 
    #             / "data"
    #             / "processed"
    #             / agente
    #             / "contenido.txt"
    #         )

    #         if archivo.exists():
    #             contenido = archivo.read_text(encoding="utf-8")

    #             partes.append(
    #                 f"""
    #                 ================
    #                 {agente.upper()}
    #                 ================

    #                 {contenido}
    #                 """
    #             )

    #         else:
    #             print(f"[RAG] No se encontro: {archivo}")

    #     return "\n\n".join(partes)    

    def obtener_agente(self, nombre: str) -> Agent:
        # if nombre not in self.agentes:
        #     print(f"[RAG] Cargando agente: {nombre}")

        #     self.agentes[nombre] = Agent(
        #         nombre,
        #         nombre,
        #         self.model
        #     )

        return self.agentes[nombre]



    def limpiar_sesiones(self):
        ahora = time.time()
        
        for sid in list(self.sessions):
            if ahora - self.sessions[sid]["last_seen"] > 3600:
                del self.sessions[sid]


    def _load_model(self):

        try:

            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                "all-MiniLM-L6-v2"
            )

            print("[RAG] Modelo cargado")

            return model

        except Exception as e:

            print(
                f"[RAG] Error cargando modelo: {e}"
            )

            return None

    # 

    def _cargar_contextos_presencialidades(self):
        base = Path(__file__).resolve().parent / "data" / "processed" / "presencialidades"

        contextos = {}

        for carpeta in base.iterdir():
            if carpeta.is_dir():
                archivo = carpeta / "contenido.txt"
                if archivo.exists():
                    contextos[carpeta.name.upper()] = archivo.read_text(encoding="utf-8")

        return contextos

    def _cargar_contextos_materias(self):
        base = Path(__file__).resolve().parent / "data" / "processed" / "cursos"

        contextos = {}

        for carpeta in base.iterdir():
            if carpeta.is_dir():
                archivo = carpeta / "contenido.txt"
                if archivo.exists():
                    contextos[carpeta.name.upper()] = archivo.read_text(encoding="utf-8")

        return contextos

    def detectar_materia(self, pregunta: str) -> Optional[str]:
        pregunta = quitar_acentos(pregunta).lower()
        for sigla, datos in MATERIAS.items():
            for alias in datos["aliases"]:
                alias_norm = quitar_acentos(alias).lower()
                if re.search(rf"\b{re.escape(alias_norm)}\b", pregunta):
                    return sigla
        return None

    def filtrar_bloques_por_materia(self, contenido: str, materia: str) -> Optional[str]:
        bloques = re.split(r"\n\s*\n", contenido)
        materia_norm = quitar_acentos(materia).lower()
        resultado = [
            b.strip() for b in bloques
            if re.search(rf"\b{re.escape(materia_norm)}\b", quitar_acentos(b).lower())
        ]
        return "\n\n".join(resultado) if resultado else None


    def filtrar_parciales_por_materia(self, contenido: str, materia: str) -> Optional[str]:
        materia_norm = quitar_acentos(materia).lower()
        parcial_actual = semestre_actual = None
        parcial_agregado = semestre_agregado = False
        resultado = []

        for linea in contenido.split("\n"):
            l = linea.strip()

            if re.match(r"\d+(er|do)\.\s*Parcial\s*-\s*Mes:", l):
                parcial_actual, parcial_agregado = l, False
                continue

            if re.match(r"\d+(er|do|to)\.\s*Semestre", l):
                semestre_actual, semestre_agregado = l, False
                continue

            m = re.match(r"-\s*(\S+)\s*\|", l)
            if m and quitar_acentos(m.group(1)).lower() == materia_norm:
                if not parcial_agregado:
                    resultado.append(f"\n{parcial_actual}")
                    parcial_agregado = True
                if not semestre_agregado:
                    resultado.append(semestre_actual)
                    semestre_agregado = True
                resultado.append(l)

        return "\n".join(resultado) if resultado else None

    def detectar_agente(self, pregunta: str) -> Optional[str]:
        pregunta_norm = quitar_acentos(pregunta.lower())
        puntajes = {}

        KEYWORDS_FUERTES = {
            "parciales": ["parcial", "parciales"],
            "docentes": ["docente", "profesor", "profesora", "quien dicta"],
            "presencialidades": ["presencial", "presencialidad", "asistencia"],
        }
    
        for agente, palabras in self.AGENTES.items():
            puntaje = 0
            for palabra in palabras:
                palabra_norm = quitar_acentos(palabra.lower())
                if palabra_norm in pregunta_norm:
                    # si la palabra esta en la lista de palabras fuertes para ese agente, suma 10, si no 1
                    if palabra_norm in KEYWORDS_FUERTES.get(agente, []):
                        puntaje += 10
                    else:
                        puntaje += 1

            # Bonificaciones
            if agente == "presencialidades" and any(kw in pregunta_norm for kw in ["hoy presencial", "mañana presencial", "cursada presencial", "dia presencial"]):
                puntaje += 5
            if agente == "calendario" and any(kw in pregunta_norm for kw in ["fecha", "feriado"]):
                puntaje += 3
            if agente == "horarios" and any(kw in pregunta_norm for kw in ["horario", "hora", "cursada", "dia"]):
                puntaje += 2

            if puntaje > 0:
                puntajes[agente] = puntaje

        if not puntajes:
            return None

        mejor_agente = max(puntajes, key=lambda a: puntajes[a])
        print(f"[ROUTER] Agente detectado: {mejor_agente} (puntaje: {puntajes[mejor_agente]})")
        return mejor_agente
    
    # -----

    def _es_saludo(self, pregunta: str) -> bool:

        saludos = [
            "hola",
            "buenas",
            "buenos dias",
            "buenas tardes",
            "buenas noches",
            "que tal",
            "como estas",
        ]

        pregunta = pregunta.lower().strip()
        pregunta = quitar_acentos(pregunta)

        return any(
            saludo in pregunta
            for saludo in saludos
        )

    
    def pregunta_es_seguimiento(self, pregunta: str) -> bool:
        
        pregunta = quitar_acentos(pregunta.lower()).strip()

        return (
            pregunta.startswith("y ")
            or pregunta.startswith("sus ")
            or pregunta.startswith("su ")
            or pregunta.startswith("tambien")
            or pregunta.startswith("también")
            or pregunta.startswith("esa")
            or pregunta.startswith("ese")
            or pregunta.startswith("eso")
        )

    # =====================

    async def answer_stream(self, question: str, session_id: str, client=None): 


        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "last_topic": None,
                "last_entity": None,
                "last_seen": time.time()
            }
        
        memoria = self.sessions[session_id]
        memoria["last_seen"] = time.time()

        self.limpiar_sesiones()
        

        question = normalizar_consulta(question)

        #  saludo 

        if self._es_saludo(question):
            yield (
                "¡Hola! Soy el asistente "
                "de la carrera Tecnólogo "
                "en Informática. "
                "¿En qué puedo ayudarte?",
                "system"
            )
                
            return

        materia = self.detectar_materia(question)
        print(f"[MATERIA] {materia}")

        if materia:
            memoria["last_entity"] = materia

        consulta_general = any(
                palabra in question.lower()
                for palabra in [
                    "semestre",
                    "materias",
                    "asignaturas",
                    "asignatura",
                    "plan de estudios"
                ]
            )

        usa_contexto = any(
            palabra in question.lower()
            for palabra in [
                "creditos",
                "créditos",
                "docente",
                "dicta",
                "horario",
                "contenido",
                "temario",
                "programa",
                "presencialidad",
                "presenciales"
            ]
        )

        if (
            not materia
            and not consulta_general
            and len(question.split()) <= 4
            and usa_contexto
            and memoria["last_entity"]
        ):
            materia = memoria["last_entity"]
            print(f"[MEMORIA] Reutilizando materia: {materia}")

        if memoria["last_entity"]:
            question = re.sub(
                r"\bsus\b",
                memoria["last_entity"],
                question,
                flags=re.IGNORECASE
                )
                
            question = re.sub(
                r"\bsu\b",
                memoria["last_entity"],
                question,
                flags=re.IGNORECASE
                )

       

        # Detectar si realmente preguntan por el contenido de una materia

        nombre_agente = self.detectar_agente(question)

        if nombre_agente:
            memoria["last_topic"] = nombre_agente

        if not nombre_agente:
            if len(question.split()) <= 4 and memoria["last_topic"]:
                nombre_agente = memoria["last_topic"]
                print(f"[MEMORIA] Reutilizando tema: {nombre_agente}")

        es_curso = (
            nombre_agente == "cursos"
            or any(
                palabra in question.lower()
                for palabra in [
                    "programa",
                    "contenido",
                    "temario",
                    "objetivos",
                    "objetivo",
                    "competencias",
                    "competencia",
                    "bibliografia",
                    "bibliografía",
                    "que se estudia",
                    "qué se estudia",
                    "creditos",
                    "materias",
                    "semestre"
                ]
            )
        )

        # Las consultas sobre semestres siempre son generales
        if consulta_general:
            materia = None

        #  búsqueda 

        if es_curso:

            if consulta_general:
                contexto = self.contexto_cursos

            elif materia:
                print(f"[RAG] Curso específico: {materia}")

                contexto = self.contextos_materias.get(materia.upper())

                if not contexto:
                    yield (
                        "No encontré información sobre esa materia.",
                        "system"
                    )
                    return

            else:
                print("[RAG] Consulta de cursos")

                agente = self.obtener_agente("cursos")

                resultados = agente.search(question)

                print(f"[SEARCH] Resultados encontrados: {len(resultados)}")

                if not resultados:
                    yield (
                        "No encontré esa información. Por favor, consultá a Secretaría.",
                        "system"
                    )
                    return

                print("\n===== RESULTADOS =====")
                for i, (chunk, score) in enumerate(resultados):
                    print(f"\n----- {i} SCORE={score} -----")
                    print(chunk)

                contexto = "\n\n".join(
                    f"[Fragmento]\n{chunk}"
                    for chunk, _ in resultados[:5]
                )

        elif nombre_agente == "presencialidades":

            if materia:
                print(f"[RAG] Presencialidades de {materia}")

                contexto = self.contextos_presencialidades.get(materia.upper())

                if not contexto:
                    yield (
                        "No encontré información sobre esa materia.",
                        "system"
                    )
                    return

            else:
                print("[RAG] Presencialidades generales")

                contexto = self.contextos.get("presencialidades", "")

        else:
            print(f"[RAG] Contexto: {nombre_agente}")
            contexto_completo = self.contextos.get(nombre_agente, "")

            if materia and nombre_agente == "parciales":
                contexto = self.filtrar_parciales_por_materia(contexto_completo, materia) or contexto_completo
            elif materia and nombre_agente in ("horarios", "docentes"):
                contexto = self.filtrar_bloques_por_materia(contexto_completo, materia) or contexto_completo
            else:
                contexto = contexto_completo


        print("\n=== CONTEXTO ===")
        print(contexto)

        print("\n=== PREGUNTA ===")
        print(question)

        print(f"[SESSION] {session_id}")
        print(f"[MEMORIA] {memoria}")

        #  prompt 

        hoy = datetime.now().strftime("%A %d/%m/%Y")
        
        prompt = f"""Hoy es {hoy}.
Contexto:
{contexto}

Pregunta: {question}

Instrucciones:
- La respuesta siempre está en el contexto.
- Buscá primero coincidencias por código de materia (por ejemplo PP, BD2, COE, MDL1).
- Si la consulta es sobre presencialidades, respondé únicamente con las fechas y horarios que aparecen en el contexto. No infieras días ni hagas resúmenes generales. Si la pregunta es general, listá todas las fechas disponibles. Si es sobre una materia, listá solo las de esa materia.
- Si encontrás una línea "Dicta: ...", respondé con el nombre del docente correspondiente.
- Si encontrás varias coincidencias, elegí la que responda exactamente la pregunta.
- Solo respondé "No encontré esa información, te sugiero consultar en Secretaría." si el dato realmente no aparece en el contexto.
- No digas que no encontraste información si el código o el nombre de la materia aparece en el contexto.
Respuesta:"""

        print("\n========== PROMPT ==========\n")
        print(prompt)
        print("\n============================\n")

        #  llamada a Ollama 

        try:

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "gemma4:e4b",
                    "prompt": prompt,
                    "stream": True,
                },
                stream=True,
                timeout=300
            )

            response.raise_for_status()

            for line in response.iter_lines():

                if line:

                    data = json.loads(
                        line.decode("utf-8")
                    )

                    if "response" in data:

                        yield (
                            data["response"],
                            "document"
                        )

        except Exception as e:
            print(f"[RAG] Error Ollama: {e}")
            import traceback
            traceback.print_exc()
            yield (
        f"Error generando respuesta aaa: {str(e)}",
        "error"
    )


    

     # Detectar si es consulta sobre cursos
#         es_curso = self.last_entity is not None

#         if not es_curso:
#             es_curso = any(
#                 palabra in question.lower()
#                 for palabra in [
#                     "materia",
#                     "materias",
#                     "curso",
#                     "cursos",
#                     "programa",
#                     "previa",
#                     "previas",
#                     "previatura",
#                     "previaturas",
#                     "asignatura",
#                     "que se estudia"
#                 ]
#         )
    
#         if es_curso:
#             # Usar agente de cursos con búsqueda semántica
#             agente = self.obtener_agente("cursos")
#             resultados = agente.search(question)
#             if not resultados:
#                 yield ("No encontré esa información. Por favor, consultá a Secretaría.", "system")
#                 return
#             contexto = "\n\n".join([f"[Fragmento]\n{chunk}" for chunk, _ in resultados[:5]])
#         else:
#             # Usar contexto fijo
#             contexto = self.contexto_fijo
        # print(f"[ROUTER] FINAL = {nombre_agente}")
        # resultados = agente.search(question)
        # print(f"[SEARCH] Resultados encontrados: {len(resultados)}")

        
            
        # if not resultados:
        #     yield ("No encontré esa información. Por favor, consultá a Secretaría. ", "system"
        #     )

        #     return

        # #  contexto 


        # print("\n===== RESULTADOS =====")
        # for i, (chunk, score) in enumerate(resultados):
        #     print(f"\n----- {i} SCORE={score} -----")
        #     print(chunk)
        # contexto = "\n\n".join(
        #     [
        #         f"[Fragmento]\n{chunk}"
        #         for chunk, _ in resultados[:5]
        #     ]
        # )