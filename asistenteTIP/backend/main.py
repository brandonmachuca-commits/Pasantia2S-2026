"""Backend FastAPI del asistente TIP, con gestión protegida de documentos."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import tempfile
import time
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePosixPath

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    # Las variables también pueden entregarse directamente en el entorno.
    pass

import edge_tts
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag import RAGSystem


BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
DOCUMENTS_DIR = BACKEND_DIR / "Documentos"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_UPLOADS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".html", ".htm"}
ALLOWED_CATEGORIES = {
    "cursos", "materias", "horarios", "docentes", "parciales", "calendario",
    "presencialidades", "info_general", "perfil_ingreso", "perfil_egreso",
}
ADMIN_TOKEN_TTL = 8 * 60 * 60
admin_tokens: dict[str, float] = {}

app = FastAPI(title="Asistente Virtual TIP")
rag = RAGSystem()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    session_id: str


class SpeakRequest(BaseModel):
    text: str


class AdminLoginRequest(BaseModel):
    password: str


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """Valida tokens temporales emitidos después de autenticar al administrador."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Inicia sesión como administrador.")
    token = authorization[7:].strip()
    expires = admin_tokens.get(token)
    if not expires or expires < time.time():
        admin_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="La sesión expiró. Vuelve a iniciar sesión.")
    return token


def _category_directory(category: str) -> Path:
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoría no permitida.")
    directory = (DOCUMENTS_DIR / category).resolve()
    if not directory.is_relative_to(DOCUMENTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Ruta de categoría inválida.")
    return directory


def _files_in_category(category: str) -> list[str]:
    directory = _category_directory(category)
    if not directory.is_dir():
        return []
    result = []
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.casefold() in SUPPORTED_UPLOADS and not path.name.startswith((".", "~$")):
            result.append(path.relative_to(directory).as_posix())
    return sorted(result, key=str.casefold)


def _validate_document(filename: str, content: bytes) -> None:
    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_UPLOADS:
        raise HTTPException(status_code=415, detail=f"Formato no admitido: {suffix or 'sin extensión'}.")
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="El archivo no parece ser un PDF válido.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if not reader.pages or reader.is_encrypted:
                raise ValueError("PDF sin páginas o protegido con contraseña")
        except ImportError:
            pass
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el PDF: {error}") from error
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if archive.testzip() or "word/document.xml" not in archive.namelist():
                    raise ValueError("estructura DOCX incompleta")
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el DOCX: {error}") from error
        try:
            from docx import Document
            Document(BytesIO(content))
        except ImportError:
            pass
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"No se pudo abrir el DOCX: {error}") from error
    else:
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content.decode("cp1252")
            except UnicodeDecodeError as error:
                raise HTTPException(status_code=400, detail="El archivo de texto no tiene una codificación compatible.") from error


@app.post("/admin/login")
async def admin_login(request: AdminLoginRequest):
    configured_password = os.getenv("ADMIN_PASSWORD", "")
    if not configured_password:
        raise HTTPException(status_code=503, detail="El panel está desactivado: falta configurar ADMIN_PASSWORD en backend/.env.")
    if not hmac.compare_digest(request.password.encode("utf-8"), configured_password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    token = secrets.token_urlsafe(32)
    now = time.time()
    for old_token, expires in list(admin_tokens.items()):
        if expires < now:
            admin_tokens.pop(old_token, None)
    admin_tokens[token] = now + ADMIN_TOKEN_TTL
    return {"ok": True, "token": token, "expira_en_segundos": ADMIN_TOKEN_TTL}


@app.post("/admin/logout")
async def admin_logout(token: str = Depends(require_admin)):
    admin_tokens.pop(token, None)
    return {"ok": True}


@app.get("/admin/documents")
async def admin_documents(_: str = Depends(require_admin)):
    categories = {}
    for category in sorted(ALLOWED_CATEGORIES):
        categories[category] = {"archivos": _files_in_category(category)}
    return {"categorias": categories}


@app.get("/speak")
async def speak_info():
    raise HTTPException(status_code=405, detail="Usa POST para generar audio.")


@app.post("/speak")
async def speak(req: SpeakRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío.")

    async def audio_stream():
        communicate = edge_tts.Communicate(req.text, "es-AR-ElenaNeural")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@app.post("/ask")
async def ask_question(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    async def event_stream():
        source = "document"
        print(f"[ASK] Pregunta: {req.question}")
        try:
            async for chunk, src in rag.answer_stream(req.question, req.session_id):
                source = src
                payload = json.dumps({"type": "chunk", "text": chunk, "source": src}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as error:
            payload = json.dumps({"type": "error", "text": str(error)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        finally:
            payload = json.dumps({"type": "done", "source": source})
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok", "agentes": list(rag.agentes.keys()), "historial_activo": rag.last_topic}


@app.get("/admin/status")
async def admin_status(_: str = Depends(require_admin)):
    categories = {}
    for name, agent in rag.agentes.items():
        status = agent.status() if hasattr(agent, "status") else {}
        categories[name] = {
            "archivos": status.get("archivos", getattr(agent, "document_count", 0)),
            "archivos_dinamicos": status.get("archivos_dinamicos", getattr(agent, "dynamic_document_count", 0)),
            "archivos_estaticos_respaldo": status.get("archivos_estaticos_respaldo", getattr(agent, "static_document_count", 0)),
            "fragmentos": status.get("fragmentos", len(getattr(agent, "chunks", []))),
            "activo": bool(getattr(agent, "chunks", [])),
        }
    return {"servidor": "ok", "categorias": categories, "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/admin")
async def admin_panel():
    page = FRONTEND_DIR / "admin.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="No se encontró el panel de administración.")
    return FileResponse(str(page), headers=NO_CACHE_HEADERS)


@app.post("/admin/upload")
async def admin_upload(
    categoria: str = Form(...),
    archivo: UploadFile = File(...),
    reemplazar: str = Form(default=""),
    _: str = Depends(require_admin),
):
    category_dir = _category_directory(categoria)
    original_name = (archivo.filename or "").replace("\\", "/").split("/")[-1].strip()
    safe_name = re.sub(r"[^\w. -]", "_", original_name, flags=re.UNICODE).strip(" .")
    if not safe_name:
        raise HTTPException(status_code=400, detail="El nombre del archivo no es válido.")
    content = await archivo.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 25 MB.")
    _validate_document(safe_name, content)

    category_dir.mkdir(parents=True, exist_ok=True)
    old_path: Path | None = None
    if reemplazar:
        if reemplazar not in _files_in_category(categoria):
            raise HTTPException(status_code=404, detail="El archivo seleccionado ya no existe en esa categoría.")
        relative = PurePosixPath(reemplazar)
        old_path = (category_dir / Path(*relative.parts)).resolve()
        if not old_path.is_relative_to(category_dir.resolve()) or not old_path.is_file():
            raise HTTPException(status_code=400, detail="La ruta de reemplazo no es válida.")
        destination = old_path.with_suffix(Path(safe_name).suffix.casefold())
    else:
        destination = category_dir / safe_name
        if destination.exists():
            raise HTTPException(status_code=409, detail="Ya existe un archivo con ese nombre; elígelo en la lista para reemplazarlo.")

    if destination.exists() and destination != old_path:
        raise HTTPException(status_code=409, detail="Ya existe el archivo destino. Selecciónalo explícitamente para reemplazarlo.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".upload-", suffix=".tmp", dir=destination.parent, delete=False) as temp_file:
            temp_name = temp_file.name
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, destination)
        if old_path is not None and old_path != destination and old_path.exists():
            old_path.unlink()
        await asyncio.to_thread(rag.reload_category, categoria)
    except Exception as error:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
        print(f"[ADMIN:UPLOAD] Error en {categoria}: {type(error).__name__}: {error}")
        raise HTTPException(status_code=500, detail=f"El archivo se guardó, pero no se pudo recargar el agente: {error}") from error

    relative_destination = destination.relative_to(category_dir).as_posix()
    return {"ok": True, "categoria": categoria, "archivo": relative_destination, "mensaje": f"Se actualizó {categoria}/{relative_destination} y se recargó el agente."}


@app.post("/admin/update/all")
async def actualizar_todo(_: str = Depends(require_admin)):
    scripts = ["process_cursos.py", "process_horarios.py", "process_parciales.py", "process_calendario.py", "process_presencialidades.py"]
    scripts_descarga = ["download_cursos.py", "download_horarios.py", "download_parciales.py", "download_calendario.py", "download_presencialidades.py"]
    base_descargar = BACKEND_DIR / "scripts" / "download"
    base_procesar = BACKEND_DIR / "scripts" / "process"
    try:
        for script in scripts_descarga:
            process = await asyncio.create_subprocess_exec("python3", str(base_descargar / script))
            if await process.wait() != 0:
                raise RuntimeError(f"Falló {script}")
        for script in scripts:
            process = await asyncio.create_subprocess_exec("python3", str(base_procesar / script))
            if await process.wait() != 0:
                raise RuntimeError(f"Falló {script}")
        await asyncio.to_thread(rag.reload_category)
        return {"ok": True, "mensaje": "Todo actualizado correctamente."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/admin/update/{categoria}")
async def actualizar_categoria(categoria: str, _: str = Depends(require_admin)):
    if categoria in {"info_general", "perfil_ingreso", "perfil_egreso"}:
        await asyncio.to_thread(rag.reload_category, categoria)
        return {"ok": True, "mensaje": f"{categoria} recargado desde sus archivos."}
    downloads = {
        "cursos": "download_cursos.py", "horarios": "download_horarios.py", "parciales": "download_parciales.py",
        "calendario": "download_calendario.py", "presencialidades": "download_presencialidades.py", "docentes": "download_docentes.py",
    }
    processors = {
        "cursos": "process_cursos.py", "horarios": "process_horarios.py", "parciales": "process_parciales.py",
        "calendario": "process_calendario.py", "presencialidades": "process_presencialidades.py", "docentes": "process_docentes.py",
    }
    if categoria not in processors:
        raise HTTPException(status_code=404, detail="Categoría inválida.")
    download_script = BACKEND_DIR / "scripts" / "download" / downloads[categoria]
    process_script = BACKEND_DIR / "scripts" / "process" / processors[categoria]
    try:
        if download_script.exists():
            proc = await asyncio.create_subprocess_exec("python3", str(download_script))
            if await proc.wait() != 0:
                raise RuntimeError(f"Falló {download_script.name}")
        elif categoria != "docentes":
            raise FileNotFoundError(f"No existe el script de descarga: {download_script}")
        if not process_script.exists():
            raise FileNotFoundError(f"No existe el script de procesamiento: {process_script}")
        proc = await asyncio.create_subprocess_exec("python3", str(process_script))
        if await proc.wait() != 0:
            raise RuntimeError(f"Falló {process_script.name}")
        await asyncio.to_thread(rag.reload_category, categoria)
        return {"ok": True, "mensaje": f"{categoria} actualizado correctamente."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/admin/reload")
async def reload(_: str = Depends(require_admin)):
    await asyncio.to_thread(rag.reload_category)
    return {"ok": True, "mensaje": "Agentes recargados."}


@app.post("/reset-memory")
async def reset_memory():
    rag.reset_memory()
    print("[MEMORY] Memoria de contexto reiniciada")
    return {"ok": True}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def root():
        return FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)

    @app.get("/{filename}")
    async def static_file(filename: str):
        path = FRONTEND_DIR / filename
        if path.is_file() and path.resolve().is_relative_to(FRONTEND_DIR.resolve()):
            return FileResponse(str(path), headers=NO_CACHE_HEADERS)
        raise HTTPException(status_code=404, detail="No encontrado.")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "═" * 55)
    print("  Asistente Virtual TIP — Backend")
    print("═" * 55)
    print("  Frontend: http://localhost:9014")
    print("═" * 55 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=9014, reload=False)
