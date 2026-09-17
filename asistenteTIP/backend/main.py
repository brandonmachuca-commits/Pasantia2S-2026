"""
AI Virtual Assistant — Backend
"""
import json
from pathlib import Path

from fastapi import Form
import edge_tts
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess

from datetime import datetime

from rag import RAGSystem

app = FastAPI(title="Asistente Virtual TIP")
rag = RAGSystem()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ── Endpoints ────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    session_id: str

class SpeakRequest(BaseModel):
    text: str


# @app.post("/upload")
# async def upload_document(file: UploadFile = File(...)):
#     content = await file.read()
#     rag.add_document(content, file.filename)
#     return {"ok": True, "message": f"'{file.filename}' procesado", "chunks": len(rag.chunks)}


@app.post("/speak")
async def speak(req: SpeakRequest):
    if not req.text.strip():
        raise HTTPException(400, "Texto vacío")

    async def audio_stream():
        communicate = edge_tts.Communicate(req.text, "es-AR-ElenaNeural")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@app.post("/ask")
async def ask_question(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía")

    async def event_stream():
        source = "training"
        full_text = ""
        print(f"[ASK] Pregunta: {req.question}")
        try:
            async for chunk, src in rag.answer_stream(req.question, req.session_id):
                source = src
                full_text += chunk
                payload = json.dumps({"type": "chunk", "text": chunk, "source": src})
                yield f"data: {payload}\n\n"
        except Exception as e:
            payload = json.dumps({"type": "error", "text": str(e)})
            yield f"data: {payload}\n\n"
        finally:
            payload = json.dumps({"type": "done", "source": source})
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agentes": list(rag.agentes.keys()),
        "historial_activo": rag.last_topic
    }


@app.get("/admin/status")
async def admin_status():
    estado = {
        "servidor": "ok",
        "agentes": {},
        "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    for nombre, agente in rag.agentes.items():
        estado["agentes"][nombre] = {
            "chunks": len(agente.chunks),
            "activo": len(agente.chunks) > 0
        }

    return estado

@app.get("/admin")
async def admin_panel():
    """Panel de administración para subir archivos"""
    admin_html = FRONTEND_DIR / "admin.html"
    if admin_html.exists():
        return FileResponse(str(admin_html))
    return {"error": "admin.html no encontrado"}

# @app.post("/admin/upload")
# async def admin_upload(
#     categoria: str = Form(...),
#     archivo: UploadFile = File(...)
# ):
#     categorias_validas = [
#         "cursos",
#         "horarios",
#         "parciales",
#         "calendario",
#         "presencialidades"
#     ]

#     if categoria not in categorias_validas:
#         return {"error": f"Categoría inválida. Use: {categorias_validas}"}

#     upload_dir = Path(__file__).parent.parent / "data" / categoria
#     upload_dir.mkdir(parents=True, exist_ok=True)

#     file_path = upload_dir / "contenido.txt"

#     content = await archivo.read()

#     with open(file_path, "wb") as f:
#         f.write(content)

#     # recargar agente automáticamente
#     if categoria in rag.agentes:
#         rag.agentes[categoria].load()

#     print(f"[UPLOAD] Archivo actualizado: {categoria}")

#     return {
#         "ok": True,
#         "categoria": categoria,
#         "archivo": archivo.filename
#     }

@app.post("/admin/update/all")
async def actualizar_todo():

    scripts = [
        "process_cursos.py",
        "process_horarios.py",
        "process_parciales.py",
        "process_calendario.py",
        "process_presencialidades.py",
    ]

    scripts_descarga = [
        "download_cursos.py",
        "download_horarios.py",
        "download_parciales.py",
        "download_calendario.py",
        "download_presencialidades.py",
    ]

    base_descargar = Path(__file__).parent / "scripts" / "download"
    base_procesar = Path(__file__).parent / "scripts" / "process"

    try:

        for script in scripts_descarga:
            subprocess.run(
                ["python3", str(base_descargar / script)],
                check=True
            )
        
        for script in scripts:
            subprocess.run(
                ["python3", str(base_procesar / script)],
                check=True
            )

        for agente in rag.agentes.values():
            agente.load()

        return {
            "ok": True,
            "mensaje": "Todo actualizado correctamente."
        }

    except subprocess.CalledProcessError as e:

        return {
            "ok": False,
            "error": str(e)
        }
    


@app.post("/admin/update/{categoria}")
async def actualizar_categoria(categoria: str):

    categorias = {
        "cursos": "process_cursos.py",
        "horarios": "process_horarios.py",
        "parciales": "process_parciales.py",
        "calendario": "process_calendario.py",
        "presencialidades": "process_presencialidades.py",
        "docentes": "process_docentes.py",
    }

    categorias_descarga = {
        "cursos": "download_cursos.py",
        "horarios": "download_horarios.py",
        "parciales": "download_parciales.py",
        "calendario": "download_calendario.py",
        "presencialidades": "download_presencialidades.py",
        "docentes": "download_horarios.py",
    }

    if categoria not in categorias:
        raise HTTPException(status_code=404, detail="Categoría inválida")

    script = (
        Path(__file__).parent
        / "scripts"
        / "process"
        / categorias[categoria]
    )

    script_descarga = (
        Path(__file__).parent
        / "scripts"
        / "download"
        / categorias_descarga[categoria]
    )

    try:
        subprocess.run(
            ["python3", str(script_descarga)],
            check=True
        )
        subprocess.run(
            ["python3", str(script)],
            check=True
        )

        if categoria in rag.agentes:
            rag.agentes[categoria].load()

        return {
            "ok": True,
            "mensaje": f"{categoria} actualizado correctamente"
        }

    except subprocess.CalledProcessError as e:

        return {
            "ok": False,
            "error": str(e)
        }
    

@app.post("/admin/reload")
async def reload():

    try:

        for agente in rag.agentes.values():
            agente.load()

        return {
            "ok": True,
            "mensaje": "Agentes recargados."
        }

    except Exception as e:

        return {
            "ok": False,
            "error": str(e)
        }


@app.post("/reset-memory")
async def reset_memory():

    rag.last_topic = None
    print("[MEMORY] Memoria de contexto reiniciada")
    return {
        "ok": True
    }

# ── Serve frontend ────────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def root():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{filename}")
    async def static_file(filename: str):
        path = FRONTEND_DIR / filename
        if path.exists() and path.is_file():
            return FileResponse(str(path))
        raise HTTPException(404, "Not found")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "═"*55)
    print("  Asistente Virtual TIP — Backend")
    print("═"*55)
    print(f"  Frontend: http://localhost:9014")
    print("═"*55 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=9014, reload=False)
