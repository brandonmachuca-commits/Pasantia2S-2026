from pathlib import Path
from collections import defaultdict
import re

import pandas as pd
from datetime import date

current_year = date.today().year

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "presencialidades"
    / "presencialidades.xlsx"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "presencialidades"
    / "contenido.txt"
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


MESES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def limpiar(valor) -> str:

    if pd.isna(valor):
        return ""

    texto = str(valor)

    texto = texto.replace("\n", " ")
    texto = texto.replace("\t", " ")

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def obtener_mes_actual(
    meses_por_columna,
    col
):

    while col >= 0:

        if col in meses_por_columna:
            return meses_por_columna[col]

        col -= 1

    return ""


def procesar_hoja(
    nombre_hoja,
    df,
    lineas
):

    lineas.append("=" * 80)
    lineas.append(nombre_hoja.upper())
    lineas.append("=" * 80)
    lineas.append("")

    meses_por_columna = {}

    # fila 0 = meses
    for col in range(1, len(df.columns)):

        valor = limpiar(
            df.iloc[0, col]
        )

        if valor in MESES:

            meses_por_columna[col] = valor

    # fila 2 = días
    dias_por_columna = {}

    for col in range(1, len(df.columns)):

        dia = limpiar(
            df.iloc[2, col]
        )

        if dia:

            mes = obtener_mes_actual(
                meses_por_columna,
                col
            )

            dias_por_columna[col] = (
                f"{dia} de {mes}"
            )

    materias = defaultdict(list)

    # desde fila 3 en adelante
    for row in range(3, len(df)):

        materia = limpiar(
            df.iloc[row, 0]
        )

        if not materia:
            continue

        for col in range(1, len(df.columns)):

            horario = limpiar(
                df.iloc[row, col]
            )

            if not horario:
                continue

            fecha = dias_por_columna.get(
                col,
                ""
            )

            if not fecha:
                continue

            if "feriado" in horario.lower():

                texto = (
                    f"{fecha}: Feriado"
                )

            else:

                texto = (
                    f"{fecha}: {horario}"
                )

            materias[materia].append(
                texto
            )

    # escribir resultado
    for materia, horarios in materias.items():

        lineas.append(materia)
        lineas.append("-" * 40)

        for h in horarios:

            lineas.append(f"  - {h}")

        lineas.append("")

    lineas.append("")


def main():

    print(
        f"[INFO] Leyendo: {INPUT_FILE}"
    )

    xls = pd.ExcelFile(INPUT_FILE)

    lineas = []

    lineas.append("=" * 80)
    lineas.append(f"PRESENCIALIDADES {current_year}")
    lineas.append("=" * 80)
    lineas.append("")

    for hoja in xls.sheet_names:

        print(f"[INFO] Procesando hoja: {hoja}")

        df = pd.read_excel(
            INPUT_FILE,
            sheet_name=hoja,
            header=None
        )

        procesar_hoja(
            hoja,
            df,
            lineas
        )

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