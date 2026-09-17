# import re
# import requests

# from bs4 import BeautifulSoup
# from pathlib import Path
# from urllib.parse import urljoin


# SITE_ROOT = "https://sites.google.com"
# SITE_URL = "https://sites.google.com/utec.edu.uy/tecnoinf"

# OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "cursos"

# OUTPUT_DIR.mkdir(
#     parents=True,
#     exist_ok=True
# )

# def obtener_url_cursos():

#     print("[INFO] Buscando página de cursos...")

#     response = requests.get(
#         SITE_URL,
#         timeout=30
#     )

#     response.raise_for_status()

#     soup = BeautifulSoup(
#         response.text,
#         "html.parser"
#     )

#     for a in soup.find_all("a", href=True):

#         texto = a.get_text(" ", strip=True).lower()
#         href = a["href"].lower()

#         if "curso" in texto or "/cursos" in href:

#             url = urljoin(SITE_ROOT, a["href"])
#             url = url.split("?")[0]

#             print(f"[OK] Página encontrada: {url}")

#             return url

#     raise Exception("No se encontró la página de cursos.")


# def limpiar_nombre(nombre: str) -> str:

#     nombre = nombre.lower()

#     nombre = re.sub(
#         r"[^a-z0-9áéíóúñ]+",
#         "-",
#         nombre
#     )

#     nombre = nombre.strip("-")

#     return nombre + ".txt"


# def limpiar_texto(texto: str) -> str:

#     lineas = texto.splitlines()

#     limpias = []

#     for linea in lineas:

#         linea = linea.strip()

#         if not linea:
#             continue

#         # evitar líneas basura
#         if len(linea) < 2:
#             continue

#         limpias.append(linea)

#     return "\n".join(limpias)


# def extraer_texto(url: str) -> str:

#     print(f"[INFO] Descargando: {url}")

#     response = requests.get(
#         url,
#         timeout=30
#     )

#     response.raise_for_status()

#     soup = BeautifulSoup(
#         response.text,
#         "html.parser"
#     )

#     # eliminar basura HTML
#     for tag in soup([
#         "script",
#         "style",
#         "nav",
#         "footer",
#         "header"
#     ]):
#         tag.decompose()

#     texto = soup.get_text(
#         separator="\n",
#         strip=True
#     )

#     return limpiar_texto(texto)


# def guardar_archivo(
#     nombre: str,
#     contenido: str
# ):

#     path = OUTPUT_DIR / nombre

#     with open(
#         path,
#         "w",
#         encoding="utf-8"
#     ) as f:

#         f.write(contenido)

#     print(f"[OK] Guardado: {path.name}")

# def guardar_indice_cursos(base_url):

#     print("[INFO] Descargando índice de cursos...")

#     texto = extraer_texto(base_url)

#     guardar_archivo(
#         "indice_cursos.txt",
#         texto
#     )


# def obtener_links_cursos(base_url):

#     print("[INFO] Obteniendo links de cursos...")

#     response = requests.get(
#         base_url,
#         timeout=30
#     )

#     response.raise_for_status()

#     soup = BeautifulSoup(
#         response.text,
#         "html.parser"
#     )

#     links = set()

#     semestres = [
#         "/1er-semestre/",
#         "/2do-semestre/",
#         "/3er-semestre/",
#         "/4to-semestre/",
#         "/5to-semestre/",
#         "/6to-semestre/",
#     ]

#     for a in soup.find_all("a", href=True):

#         href = a["href"]

#         if any(
#             semestre in href
#             for semestre in semestres
#         ):

#             url_completa = urljoin(
#                 SITE_ROOT,
#                 href
#             )

#             # eliminar authuser
#             url_completa = (
#                 url_completa
#                 .split("?")[0]
#             )

#             links.add(url_completa)

#     print(
#         f"[INFO] Cursos encontrados: "
#         f"{len(links)}"
#     )

#     return sorted(list(links))


# def descargar_cursos(base_url):

#     links = obtener_links_cursos(base_url)

#     for url in links:

#         try:

#             texto = extraer_texto(url)

#             if len(texto) < 100:
#                 print("[WARN] Contenido muy corto, omitido")
#                 continue

#             slug = url.split("/")[-1]

#             nombre_archivo = limpiar_nombre(slug)

#             guardar_archivo(
#                 nombre_archivo,
#                 texto
#             )

#         except Exception as e:
#             print(f"[ERROR] {url}")
#             print(e)

# def main():

#     print("\n" + "=" * 60)
#     print(" DESCARGA DE CURSOS - TECNÓLOGO INFORMÁTICA ")
#     print("=" * 60 + "\n")

#     base_url = obtener_url_cursos()

#     guardar_indice_cursos(base_url)

#     descargar_cursos(base_url)

#     print("\n" + "=" * 60)
#     print(" DESCARGA FINALIZADA ")
#     print("=" * 60)


# if __name__ == "__main__":
#     main()

import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin
import unicodedata


# 1. MATERIAS (copiado desde rag.py para tener los alias)


MATERIAS = {
    "PP": {
        "oficial": "Principios de Programación",
        "aliases": ["PP", "Principios de Programación", "Principios de Programacion"]
    },
    "MDL1": {
        "oficial": "Matemática Discreta y Lógica 1",
        "aliases": ["MDL1", "Matemática Discreta y Lógica 1", "Matematica Discreta y Logica 1"]
    },
    "Arq": {
        "oficial": "Arquitectura del Computador",
        "aliases": ["ARQ", "Arquitectura del Computador"]
    },
    "I1": {
        "oficial": "Inglés Técnico 1",
        "aliases": ["I1", "Inglés Técnico 1", "Ingles Tecnico 1"]
    },
    "MN": {
        "oficial": "Matemática Nivelación",
        "aliases": ["MN", "Matemática Nivelación", "Matematica Nivelacion"]
    },
    "BD1": {
        "oficial": "Bases de Datos 1",
        "aliases": ["BD1", "Bases de Datos 1"]
    },
    "I2": {
        "oficial": "Inglés Técnico 2",
        "aliases": ["I2", "Inglés Técnico 2", "Ingles Tecnico 2"]
    },
    "EDA": {
        "oficial": "Estructuras de Datos y Algoritmos",
        "aliases": ["EDA", "Estructuras de Datos y Algoritmos"]
    },
    "MDL2": {
        "oficial": "Matemática Discreta y Lógica 2",
        "aliases": ["MDL2", "Matemática Discreta y Lógica 2", "Matematica Discreta y Logica 2"]
    },
    "SO": {
        "oficial": "Sistemas Operativos",
        "aliases": ["SO", "Sistemas Operativos"]
    },
    "BD2": {
        "oficial": "Bases de Datos 2",
        "aliases": ["BD2", "Bases de Datos 2"]
    },
    "COE": {
        "oficial": "Comunicación Oral y Escrita",
        "aliases": ["COE", "Comunicación Oral y Escrita", "Comunicacion Oral y Escrita"]
    },
    "Contab": {
        "oficial": "Contabilidad",
        "aliases": ["Contab", "Contabilidad"]
    },
    "Redes": {
        "oficial": "Redes de Computadoras",
        "aliases": ["Redes", "Redes de Computadoras"]
    },
    "ProgAvanz": {
        "oficial": "Programación Avanzada",
        "aliases": ["ProgAvanz", "Prog Avanz", "Programación Avanzada", "Programacion Avanzada"]
    },
    "Adm Inf1": {
        "oficial": "Administración de Infraestructuras",
        "aliases": ["Adm Inf1", "infra 1", "Administración de Infraestructuras", "Administracion de Infraestructuras"]
    },
    "IngSoft": {
        "oficial": "Ingeniería de Software",
        "aliases": ["Ing Soft", "IngSoft", "ingenieria", "Ingeniería", "Ingenieria de Software", "Ingeniería de Software"]
    },
    "PyE": {
        "oficial": "Probabilidad y Estadística",
        "aliases": ["PyE", "probabilidad", "estadistica", "Probabilidad y Estadistica", "Probabilidad y Estadística"]
    },
    "ProgAplic": {
        "oficial": "Programación de Aplicaciones",
        "aliases": ["ProgAplic", "Programacion de Aplicaciones", "Programación de Aplicaciones"]
    },
    "RPyL": {
        "oficial": "Relaciones Personales y Laborales",
        "aliases": ["RPyL", "Relaciones Personales y Laborales"]
    },
    "Internet Ricas": {
        "oficial": "Taller de Aplicaciones de Internet Ricas",
        "aliases": ["RIA", "Internet Ricas", "Taller de Aplicaciones de Internet Ricas"]
    },
    "JAVA EE": {
        "oficial": "Taller de Sistemas de Información Java EE",
        "aliases": ["JAVA EE", "JAVAEE", "Java", "Java EE", "Taller de Sistemas de Información Java EE"]
    },
    "ADMINF II": {
        "oficial": "Administración de Infraestructuras 2",
        "aliases": ["ADMINFII", "infra 2", "Administración de Infraestructuras 2", "Administracion de Infraestructuras 2"]
    },
    "Pasantia": {
        "oficial": "Pasantia Laboral",
        "aliases": ["Pasantia", "pasantia", "Pasantia Laboral"]
    },
    "PHP": {
        "oficial": "Taller de Desarrollo de Aplicaciones Web con PHP",
        "aliases": ["PHP", "Taller de Desarrollo de Aplicaciones Web con PHP"]
    },
    "Móviles": {
        "oficial": "Taller de Desarrollo de Aplicaciones Para Dispositivos Móviles",
        "aliases": ["Móviles", "moviles", "android", "Taller de Desarrollo de Aplicaciones Para Dispositivos Móviles"]
    },
    "JyM": {
        "oficial": "Sistemas de Gestión de Contenidos",
        "aliases": ["JyM", "jym", "Sistemas de Gestión de Contenidos", "Sistemas de Gestion de Contenidos"]
    },
    ".NET": {
        "oficial": "Taller de Sistemas de Información .NET",
        "aliases": [".NET", "dotnet", "Taller de Sistemas de Información .NET", "Taller de Sistemas de Informacion .NET"]
    },
    "Control": {
        "oficial": "Introducción a los Sistemas de Control",
        "aliases": ["Control", "control", "Introducción a los Sistemas de Control", "Introduccion a los Sistemas de Control"]
    },
    "Proyecto": {
        "oficial": "Proyecto",
        "aliases": ["Proyecto", "proyecto"]
    },
    "Taller Gestión de la Innovación T": {
        "oficial": "Taller de Gestión de la Innovación en Tecnologías",
        "aliases": ["Innovación", "innovacion", "Taller de Gestión de la Innovación en Tecnologías", "Taller de Gestion de la Innovacion en Tecnologias"]
    },
    "Juegos": {
        "oficial": "Introducción al Desarrollo de Juegos",
        "aliases": ["Juegos", "juegos", "Introducción al Desarrollo de Juegos", "Introduccion al Desarrollo de Juegos"]
    },
}

# 2. Configuración


SITE_ROOT = "https://sites.google.com"
SITE_URL = "https://sites.google.com/utec.edu.uy/tecnoinf"

# Donde se van a guardar las carpetas de cada materia
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "processed" / "cursos"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 3. Funciones auxiliares

def quitar_acentos(texto: str) -> str:
    """Elimina tildes de un texto."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_slug(slug: str) -> str:
    """
    Convierte un slug de URL en una cadena normalizada (sin tildes, minúsculas,
    reemplazando guiones por espacios) para facilitar la búsqueda en MATERIAS.
    """
    slug = slug.replace("-", " ").lower()
    slug = quitar_acentos(slug)
    return slug


def mapear_url_a_materia(url: str) -> tuple:
    """
    Intenta encontrar la materia correspondiente a una URL.
    Retorna (sigla, nombre_oficial) o (None, None) si no se encuentra.
    """
    slug = url.split("/")[-1]
    slug_norm = normalizar_slug(slug)

    for sigla, datos in MATERIAS.items():
        for alias in datos["aliases"]:
            alias_norm = quitar_acentos(alias.lower())

            if slug_norm in alias_norm or alias_norm in slug_norm:
                return sigla, datos["oficial"]

    return None, None


def limpiar_texto(texto: str) -> str:
    """Limpia y formatea el texto extraído."""
    lineas = texto.splitlines()
    limpias = []
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        if len(linea) < 2:
            continue
        if re.match(r"^[\d\s]+$", linea):
            continue
        limpias.append(linea)
    return "\n".join(limpias)


def extraer_texto(url: str) -> str:
    """Descarga y extrae el texto limpio de una URL."""
    print(f"  [INFO] Descargando: {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    texto = soup.get_text(separator="\n", strip=True)
    return limpiar_texto(texto)


def obtener_url_cursos() -> str:
    """Encuentra la URL de la página principal de cursos."""
    print("[INFO] Buscando página de cursos...")
    response = requests.get(SITE_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for a in soup.find_all("a", href=True):
        texto = a.get_text(" ", strip=True).lower()
        href = a["href"].lower()
        if "curso" in texto or "/cursos" in href:
            url = urljoin(SITE_ROOT, a["href"])
            url = url.split("?")[0]
            print(f"[OK] Página encontrada: {url}")
            return url

    raise Exception("No se encontró la página de cursos.")


def obtener_links_cursos(base_url: str) -> list:
    """Obtiene todos los enlaces a páginas de cursos desde la página principal."""
    print("[INFO] Obteniendo links de cursos...")
    response = requests.get(base_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    links = set()
    semestres = [
        "/1er-semestre/",
        "/2do-semestre/",
        "/3er-semestre/",
        "/4to-semestre/",
        "/5to-semestre/",
        "/6to-semestre/",
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(semestre in href for semestre in semestres):
            url_completa = urljoin(SITE_ROOT, href)
            url_completa = url_completa.split("?")[0]
            links.add(url_completa)

    print(f"[INFO] Cursos encontrados: {len(links)}")
    return sorted(list(links))


def guardar_contexto_materia(sigla: str, contenido: str):
    """Guarda el contenido en data/processed/cursos/{sigla}/contenido.txt"""
    carpeta = OUTPUT_DIR / sigla
    carpeta.mkdir(parents=True, exist_ok=True)

    archivo = carpeta / "contenido.txt"
    with open(archivo, "w", encoding="utf-8") as f:
        f.write(contenido)

    print(f"[OK] Guardado: {archivo}")

# 4. Función principal

def main():
    print("\n" + "=" * 60)
    print(" DESCARGA DE CURSOS - TECNÓLOGO INFORMÁTICA ")
    print("=" * 60 + "\n")

    # 1. Obtener la página principal de cursos
    base_url = obtener_url_cursos()

    # 2. Obtener todos los enlaces de cursos
    links = obtener_links_cursos(base_url)

    # 3. Para cada enlace, extraer texto y guardar en la carpeta correspondiente
    for url in links:
        try:
            # Extraer el slug de la URL
            slug = url.split("/")[-1]
            if not slug:
                slug = url.split("/")[-2]

            # Intentar mapear a una materia
            sigla, nombre = mapear_url_a_materia(url)

            if sigla:
                print(f"\n[PROC] Materia: {sigla} - {nombre}")
                texto = extraer_texto(url)

                if len(texto) < 100:
                    print("  [WARN] Contenido muy corto, omitido")
                    continue

                # Guardar en la carpeta de la materia
                guardar_contexto_materia(sigla, texto)
            else:
                print(f"\n[WARN] No se pudo mapear la URL: {url}")


        except Exception as e:
            print(f"[ERROR] {url}")
            print(e)

    print("\n" + "=" * 60)
    print(" DESCARGA FINALIZADA ")
    print("=" * 60)


if __name__ == "__main__":
    main()