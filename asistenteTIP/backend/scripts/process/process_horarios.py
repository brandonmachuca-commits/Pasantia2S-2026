from pathlib import Path
from collections import defaultdict
import re
import unicodedata

from docx import Document
from datetime import date

current_year = date.today().year

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "horarios"
    / "horarios.docx"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "horarios"
    / "contenido.txt"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


DIAS = [
    "LUNES",
    "MARTES",
    "MIÉRCOLES",
    "JUEVES",
    "VIERNES",
    "SÁBADO",
]

def clave_materia(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.upper()
    texto = re.sub(r"\s+", "", texto)
    return texto

def limpiar(texto: str) -> str:

    texto = texto.replace("\n", " ")
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()

NOMBRES_MATERIAS = {}
def normalizar_materia(materia: str) -> str:

    clave = clave_materia(materia)

    if clave not in NOMBRES_MATERIAS:
        NOMBRES_MATERIAS[clave] = materia.strip()

    return NOMBRES_MATERIAS[clave]

def es_hora(valor: str) -> bool:

    valor = valor.strip()

    return valor.isdigit() and 0 <= int(valor) <= 23


def formatear_hora(hora: int) -> str:

    return f"{hora:02d}:00"


def extraer_tablas(doc: Document):

    tablas = []

    for table in doc.tables:

        filas = []

        for row in table.rows:

            fila = []

            for cell in row.cells:

                texto = limpiar(cell.text)

                fila.append(texto)

            filas.append(fila)

        tablas.append(filas)

    return tablas


def detectar_semestre(texto: str) -> str:

    texto = texto.upper()

    if "PRIMER" in texto:
        return "Primer Semestre"

    if "TERCER" in texto:
        return "Tercer Semestre"

    if "QUINTO" in texto:
        return "Quinto Semestre"

    if "SEGUNDO" in texto:
        return "Segundo Semestre"

    if "CUARTO" in texto:
        return "Cuarto Semestre"

    if "SEXTO" in texto:
        return "Sexto Semestre"

    return "Semestre"


def obtener_dias(header):

    dias = []

    for cell in header:

        texto = limpiar(cell).upper()

        encontrado = None

        for dia in DIAS:

            if dia in texto:
                encontrado = dia.title()
                break

        dias.append(encontrado)

    return dias


def agregar_bloque(
    resultado,
    semestre,
    dia,
    materia,
    inicio,
    fin
):

    if not materia:
        return

    if inicio == fin:

        horario = f"{formatear_hora(inicio)}"

    else:

        horario = (
            f"{formatear_hora(inicio)} "
            f"a "
            f"{formatear_hora(fin + 1)}"
        )

    resultado[semestre][materia].append(
        f"{dia}: {horario}"
    )


def procesar_tabla(tabla, resultado):

    if len(tabla) < 3:
        return

    semestre = detectar_semestre(" ".join(tabla[0]))

    header = None

    for fila in tabla:

        texto = " ".join(fila).upper()

        if "LUNES" in texto or "MARTES" in texto:

            header = fila
            break

    if not header:
        return

    dias = obtener_dias(header)

    datos = []

    header_encontrado = False

    for fila in tabla:

        texto = " ".join(fila).upper()

        if header_encontrado:

            if fila and es_hora(fila[0]):
                datos.append(fila)

        if fila == header:
            header_encontrado = True

    materias = defaultdict(list)

    for fila in datos:

        if not fila:
            continue

        hora_txt = fila[0]

        if not es_hora(hora_txt):
            continue

        hora = int(hora_txt)

        for i in range(1, min(len(fila), len(dias))):

            dia = dias[i]

            if not dia:
                continue

            materia = limpiar(fila[i])
            materia = normalizar_materia(materia)

            if not materia:
                continue

            materias[(semestre, dia, materia)].append(hora)

    for (semestre, dia, materia), horas in materias.items():

        horas = sorted(set(horas))

        inicio = horas[0]
        fin = horas[0]

        bloques = []

        for h in horas[1:]:

            if h == fin + 1:

                fin = h

            else:

                bloques.append((inicio, fin))

                inicio = h
                fin = h

        bloques.append((inicio, fin))

        for inicio, fin in bloques:

            agregar_bloque(
                resultado,
                semestre,
                dia,
                materia,
                inicio,
                fin
            )


def main():

    print(f"[INFO] Leyendo: {INPUT_FILE}")

    doc = Document(INPUT_FILE)

    tablas = extraer_tablas(doc)

    resultado = defaultdict(
        lambda: defaultdict(list)
    )

    for tabla in tablas:

        procesar_tabla(
            tabla,
            resultado
        )

    lineas = []

    lineas.append("=" * 80)
    lineas.append(f"HORARIOS {current_year}")
    lineas.append("=" * 80)
    lineas.append("")

    for semestre, materias in resultado.items():

        lineas.append(f"{semestre}")
        lineas.append("-" * 50)
        lineas.append("")

        for materia, horarios in sorted(materias.items()):

            lineas.append(f"{materia}")

            for horario in horarios:

                lineas.append(f"  - {horario}")

            lineas.append("")

        lineas.append("")

    contenido = "\n".join(lineas)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(contenido)

    print(f"[OK] Archivo generado:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()