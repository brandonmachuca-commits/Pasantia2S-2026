# download_presencialidades.py

import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


SITE_URL = "https://sites.google.com/utec.edu.uy/tecnoinf"

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "presencialidades"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "presencialidades.xlsx"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

def obtener_url_pagina(nombre: str):

    r = requests.get(SITE_URL, headers=HEADERS)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    nombre = nombre.lower()

    for a in soup.find_all("a", href=True):

        texto = a.get_text(" ", strip=True).lower()
        href = a["href"].lower()

        if nombre in texto or nombre in href:

            return urljoin(SITE_URL, a["href"])

    raise Exception(f"No se encontró la página '{nombre}'.")


def obtener_sheet_id(html: str):

    patrones = [
        r'https://docs\.google\.com/spreadsheets/d/([^/]+)/',
        r'https://drive\.google\.com/file/d/([^/]+)/'
    ]

    for patron in patrones:

        match = re.search(patron, html)

        if match:
            return match.group(1)

    return None


def descargar_excel(sheet_id: str):

    # EXPORT REAL DE GOOGLE SHEETS
    download_url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{sheet_id}/export?format=xlsx"
    )

    print("[INFO] Descargando Excel...")

    response = requests.get(
        download_url,
        headers=HEADERS,
        stream=True
    )

    response.raise_for_status()

    with open(OUTPUT_FILE, "wb") as f:

        for chunk in response.iter_content(8192):

            if chunk:
                f.write(chunk)

    print(f"[OK] Excel guardado en:")
    print(OUTPUT_FILE.resolve())


def main():

    print("[INFO] Descargando página de presencialidades...")

    url = obtener_url_pagina("presencialidades")

    response = requests.get(
        url,
        headers=HEADERS
    )

    response.raise_for_status()

    html = response.text

    print("[INFO] Buscando Google Sheets incrustado...")

    sheet_id = obtener_sheet_id(html)

    if not sheet_id:
        print("[ERROR] No se encontró el Google Sheets")
        return

    print(f"[INFO] Sheet ID encontrado: {sheet_id}")

    descargar_excel(sheet_id)


if __name__ == "__main__":
    main()