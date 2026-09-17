# download_parciales.py

import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


SITE_URL = "https://sites.google.com/utec.edu.uy/tecnoinf"

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "parciales"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "parciales.docx"



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

def obtener_link_drive(html: str):

    # Busca links de Google Drive incrustados
    patrones = [
        r'https://drive\.google\.com/file/d/([^/]+)/',
        r'https://drive\.google\.com/open\?id=([^"&]+)',
        r'"https://drive\.google\.com/uc\?id=([^"&]+)'
    ]

    for patron in patrones:

        match = re.search(patron, html)

        if match:
            return match.group(1)

    return None


def descargar_archivo(file_id: str):

    download_url = (
        f"https://drive.google.com/uc?export=download&id={file_id}"
    )

    print("[INFO] Descargando DOCX desde Drive...")

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

    print(f"[OK] Archivo guardado en:")
    print(OUTPUT_FILE.resolve())


def main():

    print("[INFO] Descargando página de parciales...")

    url = obtener_url_pagina("parciales")

    response = requests.get(
        url,
        headers=HEADERS
    )

    response.raise_for_status()

    html = response.text

    print("[INFO] Buscando archivo de Drive incrustado...")

    file_id = obtener_link_drive(html)

    if not file_id:
        print("[ERROR] No se encontró el archivo de Drive")
        return

    print(f"[INFO] File ID encontrado: {file_id}")

    descargar_archivo(file_id)


if __name__ == "__main__":
    main()