"""Agente especialista: carga documentos, crea fragmentos y recupera evidencia."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

try:
    import numpy as np
except ImportError:  # La búsqueda por palabras sigue funcionando sin NumPy.
    np = None


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", texto)


class Agent:
    """Busca en una categoría. Mantiene el contrato Agent.search() del backend."""

    CARPETAS_COMPATIBLES = {
        "cursos": ("cursos", "presencialidades"),
        "horarios": ("horarios",),
        "info_general": ("info_general", "calendario"),
    }

    def __init__(self, nombre: str, carpeta: str, model=None):
        self.nombre = nombre
        self.carpeta = carpeta
        self.model = model
        self.tipo_busqueda = "semantico" if nombre == "cursos" else "keywords"
        self.chunks: list[str] = []
        self.chunk_sources: list[str] = []
        self.embeddings = None
        self.load()

    def _candidate_roots(self) -> list[Path]:
        """Ubica tanto los datos procesados del backend como los TXT del prototipo."""
        here = Path(__file__).resolve().parent
        project = here.parent if here.name.lower() == "backend" else here
        processed = here / "data" / "processed"
        if not processed.exists():
            processed = project / "backend" / "data" / "processed"

        names = self.CARPETAS_COMPATIBLES.get(self.carpeta, (self.carpeta,))
        roots = [processed / name for name in names]
        for name in names:
            carpeta_procesada = processed / name
            tiene_procesado = bool(list(carpeta_procesada.rglob("*.txt"))) if carpeta_procesada.is_dir() else False
            # Conserva el corpus ya procesado. El prototipo aporta como respaldo
            # los perfiles y la tabla general nueva si aún no existen en processed.
            if not tiene_procesado or self.carpeta == "info_general":
                roots.append(project / "backend-v2" / "Documentos" / name)
        roots.extend(here / "Documentos" / name for name in names)
        # No leer dos veces la misma ubicación.
        return list(dict.fromkeys(path.resolve() for path in roots))

    def _files_in(self, root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        # Incluye archivos de texto del nivel raíz y todas sus subcarpetas.
        files = sorted(root.rglob("*.txt"))
        return files

    def load(self):
        self.chunks = []
        self.chunk_sources = []
        self.embeddings = None
        vistos: set[Path] = set()
        chunks_vistos: set[str] = set()

        for root in self._candidate_roots():
            for archivo in self._files_in(root):
                archivo = archivo.resolve()
                if archivo in vistos:
                    continue
                vistos.add(archivo)
                try:
                    texto = archivo.read_text(encoding="utf-8-sig", errors="replace")
                except OSError as error:
                    print(f"[AGENT:{self.nombre}] No se pudo leer {archivo.name}: {error}")
                    continue
                etiqueta = f"{root.name}/{archivo.relative_to(root).as_posix()}"
                for chunk in self._chunk_text(texto):
                    clave = _normalizar(chunk)
                    if clave in chunks_vistos:
                        continue
                    chunks_vistos.add(clave)
                    self.chunks.append(chunk)
                    self.chunk_sources.append(etiqueta)

        if self.model is not None and self.tipo_busqueda == "semantico" and self.chunks:
            try:
                self.embeddings = self.model.encode(
                    self.chunks, convert_to_numpy=True, show_progress_bar=False
                )
            except Exception as error:
                print(f"[AGENT:{self.nombre}] Búsqueda semántica no disponible: {error}")
                self.embeddings = None

        print(f"[AGENT:{self.nombre}] {len(self.chunks)} fragmentos cargados")
        if not self.chunks:
            print(f"[AGENT:{self.nombre}] No se encontraron documentos para {self.carpeta}")

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
        text = text.replace("\r", "").strip()
        if not text:
            return []

        chunks: list[str] = []
        bloques = re.split(r"(?:={8,}|-{8,}|\n\s*\n)", text)
        for bloque in bloques:
            bloque = bloque.strip()
            if len(bloque) < 15:
                continue
            inicio = 0
            while inicio < len(bloque):
                fin = min(inicio + max_chars, len(bloque))
                if fin < len(bloque):
                    corte = max(bloque.rfind("\n", inicio, fin), bloque.rfind(". ", inicio, fin))
                    if corte > inicio + max_chars // 2:
                        fin = corte + (1 if bloque[corte:corte + 2] == ". " else 0)
                fragmento = bloque[inicio:fin].strip()
                if len(fragmento) >= 15:
                    chunks.append(fragmento)
                if fin >= len(bloque):
                    break
                inicio = max(inicio + 1, fin - overlap)
        return chunks

    def search_with_source(
        self,
        query: str,
        top_k: int = 4,
        threshold: float = 0.18,
        must_contain: Optional[list[str]] = None,
    ) -> list[dict]:
        if not self.chunks or top_k <= 0:
            return []

        query_norm = _normalizar(query)
        palabras = [
            p for p in query_norm.split()
            if len(p) > 2 and p not in {
                "para", "por", "con", "que", "como", "cuando", "donde",
                "quien", "cual", "materia", "asignatura", "decime", "dime",
                "quiero", "saber", "puedes", "podrias", "necesito",
            }
        ]
        scores = [0.0] * len(self.chunks)
        admitidos = [True] * len(self.chunks)
        for i, chunk in enumerate(self.chunks):
            texto = re.sub(r"[^\w]+", " ", _normalizar(
                chunk + " " + self.chunk_sources[i]
            )).strip()
            if must_contain:
                entidades = [
                    re.sub(r"[^\w]+", " ", _normalizar(alias)).strip()
                    for alias in must_contain if alias
                ]
                if not any(
                    re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", texto)
                    for alias in entidades if alias
                ):
                    admitidos[i] = False
                    continue
            if query_norm and len(query_norm) > 3 and query_norm in texto:
                scores[i] += 8.0
            for palabra in palabras:
                if re.search(rf"\b{re.escape(palabra)}\b", texto):
                    scores[i] += 2.0 if len(palabra) >= 5 else 1.0

        if (
            self.tipo_busqueda == "semantico"
            and self.model is not None
            and self.embeddings is not None
            and np is not None
        ):
            try:
                q_emb = self.model.encode([query], convert_to_numpy=True)
                emb = np.asarray(self.embeddings)
                denom = np.linalg.norm(emb, axis=1) * np.linalg.norm(q_emb) + 1e-8
                sims = (np.dot(emb, q_emb.T).flatten() / denom).tolist()
                scores = [
                    max(score, float(sim) * 5.0) if admitido else 0.0
                    for score, sim, admitido in zip(scores, sims, admitidos)
                ]
            except Exception as error:
                print(f"[AGENT:{self.nombre}] Falló búsqueda semántica: {error}")

        ranking = sorted(enumerate(scores), key=lambda par: par[1], reverse=True)
        resultados = []
        for index, score in ranking:
            if score <= 0 or (self.tipo_busqueda == "semantico" and score < threshold):
                continue
            resultados.append({
                "chunk": self.chunks[index],
                "fuente": self.chunk_sources[index],
                "score": float(score),
                "categoria": self.nombre,
            })
            if len(resultados) >= top_k:
                break
        return resultados

    def search(self, query: str, top_k: int = 5, threshold: float = 0.22):
        """Compatibilidad con el contrato anterior: lista de (fragmento, puntaje)."""
        return [
            (r["chunk"], r["score"])
            for r in self.search_with_source(query, top_k=top_k, threshold=threshold)
        ]
