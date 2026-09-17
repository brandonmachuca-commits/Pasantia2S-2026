from pathlib import Path
import re

from docx import Document
from datetime import date

current_year = date.today().year

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "parciales"
    / "parciales.docx"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "parciales"
    / "contenido.txt"
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


def limpiar(texto: str) -> str:

    texto = texto.replace("\n", " ")
    texto = texto.replace("\t", " ")

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def obtener_texto_tabla(table):

    filas = []

    for row in table.rows:

        fila = []

        for cell in row.cells:

            fila.append(
                limpiar(cell.text)
            )

        filas.append(fila)

    return filas


def main():

    print(f"[INFO] Leyendo: {INPUT_FILE}")

    doc = Document(INPUT_FILE)

    lineas = []

    lineas.append("=" * 80)
    lineas.append(f"PARCIALES {current_year}")
    lineas.append("=" * 80)
    lineas.append("")

    for table in doc.tables:

        filas = obtener_texto_tabla(table)

        parcial_actual = ""

        dias = []

        i = 0

        while i < len(filas):

            fila = filas[i]

            texto_fila = " ".join(fila)

            # detectar parcial
            if "PARCIAL" in texto_fila.upper():

                parcial_actual = texto_fila.strip()

                lineas.append(parcial_actual)
                lineas.append("-" * 50)

            # detectar fila de días
            if any(
                dia in texto_fila
                for dia in [
                    "Lunes",
                    "Martes",
                    "Miércoles",
                    "Jueves",
                    "Viernes"
                ]
            ):

                dias = fila[1:]

            # detectar semestre
            if (
                "Semestre" in texto_fila
                and "Horario" not in texto_fila
            ):

                semestre = fila[0]

                materias = fila[1:]

                horario_fila = []

                # la fila siguiente suele ser horarios
                if i + 1 < len(filas):

                    prox = filas[i + 1]

                    if (
                        len(prox) > 0
                        and "Horario" in prox[0]
                    ):

                        horario_fila = prox[1:]

                lineas.append("")
                lineas.append(semestre)

                for idx, materia in enumerate(materias):

                    materia = limpiar(materia)

                    if not materia:
                        continue

                    dia = ""

                    if idx < len(dias):

                        dia = dias[idx]

                    horario = ""

                    if idx < len(horario_fila):

                        horario = horario_fila[idx]

                    linea = f"- {materia}"

                    if dia:
                        linea += f" | {dia}"

                    if horario:
                        linea += f" | Horario: {horario}"

                    lineas.append(linea)

            i += 1

        lineas.append("")

    contenido = "\n".join(lineas)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(contenido)

    print("[OK] Archivo generado:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()