# download_horarios.py

import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


SITE_URL = "https://sites.google.com/utec.edu.uy/tecnoinf"

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "horarios"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DOCENTES = Path(__file__).parent.parent.parent / "data" / "raw" / "docentes"
OUTPUT_DOCENTES.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "horarios.docx"
OUTPUT_DOCENTES_FILE = OUTPUT_DOCENTES / "docentes.xlsx"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

def obtener_url_horarios():
    """
    Busca automáticamente la página de horarios desde la página principal.
    """

    print("[INFO] Buscando página de horarios...")

    r = requests.get(SITE_URL, headers=HEADERS)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):

        texto = a.get_text(" ", strip=True).lower()
        href = a["href"].lower()

        if "horario" in texto or "horario" in href:

            url = urljoin(SITE_URL, a["href"])

            print(f"[OK] Página encontrada: {url}")

            return url

    raise Exception("No se encontró la página de horarios.")

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


def extraer_spreadsheet_id(html: str):
    """
    Busca IDs de Google Sheets embebidos en Google Sites.
    """

    patrones = [
        r"/spreadsheets/d/([a-zA-Z0-9-_]+)",
        r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)",
        r"spreadsheetId=([a-zA-Z0-9-_]+)"
    ]

    for patron in patrones:
        match = re.search(patron, html)
        if match:
            return match.group(1)

    return None


def descargar_sheet_as_xlsx(sheet_id: str):

    # Export oficial de Google Sheets
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
        f"?format=xlsx"
    )

    print("[INFO] Descargando spreadsheet como XLSX...")

    r = requests.get(url, headers=HEADERS, stream=True)
    r.raise_for_status()

    with open(OUTPUT_DOCENTES_FILE, "wb") as f:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)

    print("[OK] Archivo guardado en:")
    print(OUTPUT_DOCENTES_FILE.resolve())

def main():

    print("[INFO] Descargando página de horarios...")

    url = obtener_url_horarios()

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
    
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()

    html = r.text

    print("[INFO] Buscando Google Spreadsheet embebido...")

    sheet_id = extraer_spreadsheet_id(html)

    if not sheet_id:
        print("[ERROR] No se encontró spreadsheet embebida.")
        print("Puede estar cargada dinámicamente (JS).")
        return

    print(f"[INFO] Spreadsheet ID: {sheet_id}")

    descargar_sheet_as_xlsx(sheet_id)


if __name__ == "__main__":
    main()