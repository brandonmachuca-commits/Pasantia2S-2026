# process_cursos.py

import re
from pathlib import Path
from datetime import date

current_year = date.today().year

INPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "cursos"
OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "processed" / "cursos" /"contenido.txt" 

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def limpiar_texto(texto: str) -> str:

    # eliminar basura típica de Google Sites
    basura = [
        "Search this site",
        "Skip to main content",
        "Skip to navigation",
        "Embedded Files",
        "Report abuse",
        "Page details",
        "Page updated",
    ]

    for b in basura:
        texto = texto.replace(b, "")

    # eliminar espacios repetidos
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)

    # eliminar tabs
    texto = texto.replace("\t", " ")

    # espacios múltiples
    texto = re.sub(r"[ ]{2,}", " ", texto)

    return texto.strip()


def obtener_titulo(texto: str) -> str:

    lineas = texto.splitlines()

    for linea in lineas:

        linea = linea.strip()

        if len(linea) > 5:
            return linea

    return "Curso"


def procesar_archivo(path: Path) -> str:

    print(f"[INFO] Procesando: {path.name}")

    with open(path, "r", encoding="utf-8") as f:
        texto = f.read()

    texto = limpiar_texto(texto)

    titulo = obtener_titulo(texto)

    contenido = (
        "\n"
        + "=" * 80
        + "\n"
        + f"CURSO: {titulo}\n"
        + "=" * 80
        + "\n\n"
        + texto
        + "\n\n"
    )

    return contenido


def main():

    archivos = sorted(INPUT_DIR.glob("*.txt"))

    if not archivos:
        print("[ERROR] No hay archivos en:")
        print(INPUT_DIR.resolve())
        return

    resultado_final = []

    # índice inicial
    resultado_final.append(
        """
================================================================================
ÍNDICE DE CURSOS
================================================================================

1er Semestre
- Arquitectura del Computador
- Inglés Técnico 1
- Matemática
- Matemática Discreta y Lógica 1
- Principios de Programación

2do Semestre
- Bases de Datos 1
- Inglés Técnico 2
- Estructuras de Datos y Algoritmos
- Matemática Discreta y Lógica 2
- Sistemas Operativos

3er Semestre
- Bases de Datos 2
- Comunicación Oral y Escrita
- Contabilidad
- Redes de Computadoras
- Programación Avanzada

4to Semestre
- Administración de Infraestructuras
- Ingeniería de Software
- Probabilidad y Estadística
- Programación de Aplicaciones
- Relaciones Personales y Laborales

5to Semestre
- Taller de Aplicaciones de Internet Ricas
- Taller de Sistemas de Información Java EE
- Administración de Infraestructuras 2
- Pasantía Laboral
- Taller de Desarrollo de Aplicaciones Web con PHP
- Taller de Aplicaciones Para Dispositivos Móviles

6to Semestre
- Sistemas de Gestión de Contenidos
- Taller de Sistemas de Información .NET
- Introducción a los Sistemas de Control
- Proyecto
- Taller de Gestión de la Innovación en Tecnologías
- Introducción al Desarrollo de Juegos
"""
    )

    # cursos
    for archivo in archivos:

        try:

            contenido = procesar_archivo(archivo)

            resultado_final.append(contenido)

        except Exception as e:

            print(f"[ERROR] {archivo.name}")
            print(e)

    # guardar resultado
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        f.write("\n".join(resultado_final))

    print("\n[OK] contenido.txt generado:")
    print(OUTPUT_FILE.resolve())


if __name__ == "__main__":
    main()