"""Carga y recuperación de documentos dinámicos de backend/Documentos/<categoría>."""

from __future__ import annotations

import html
import re
import threading
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

try:
    import numpy as np
except ImportError:
    np = None


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".csv", ".docx", ".html", ".htm"}
STATIC_FALLBACK_CATEGORIES = {
    "cursos", "materias", "info_general", "perfil_ingreso", "perfil_egreso",
}
STATIC_CATEGORY_ALIASES = {
    "cursos": ("cursos", "materias"),
    "materias": ("materias", "cursos"),
}
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 120


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _tokens(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalizar(texto))


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self.partes.append(data)


class Agent:
    """Indexa todos los archivos de una categoría y conserva sus rutas de origen.

    La instancia se limita a una carpeta inmediata dentro de Documentos, pero
    busca archivos recursivamente en sus subcarpetas. load() reconstruye el
    índice en memoria para que el panel de administración pueda recargarlo.
    """

    def __init__(
        self,
        nombre: str,
        carpeta: str,
        model=None,
        documents_root: Optional[str | Path] = None,
        static_root: Optional[str | Path] = None,
    ):
        self.nombre = str(nombre)
        self.carpeta = str(carpeta)
        self.model = model
        self.documents_root = Path(documents_root or (Path(__file__).resolve().parent / "Documentos")).resolve()
        self.ruta = (self.documents_root / self.carpeta).resolve()
        self.static_root = Path(static_root).resolve() if static_root else None
        self.static_categories = (
            STATIC_CATEGORY_ALIASES.get(self.carpeta.casefold(), (self.carpeta,))
            if self.carpeta.casefold() in STATIC_FALLBACK_CATEGORIES
            else ()
        )
        self.tipo_busqueda = "semantico" if model is not None else "texto"
        self.chunks: list[str] = []
        self.chunk_sources: list[str] = []
        self.chunk_tiers: list[str] = []
        self.embeddings = None
        self.files_loaded: list[str] = []
        self.load_errors: list[str] = []
        self.document_count = 0
        self.dynamic_document_count = 0
        self.static_document_count = 0
        self._lock = threading.RLock()
        self.load()

    def _files_in(self, root: Optional[Path] = None) -> list[Path]:
        root = root or self.ruta
        if not root.is_dir():
            return []
        return sorted(
            (
                path for path in root.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in SUPPORTED_EXTENSIONS
                and not path.name.startswith(("~$", "."))
                and not path.name.casefold().endswith((".tmp", ".part"))
            ),
            key=lambda path: str(path).casefold(),
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _read_file(self, path: Path) -> list[tuple[str, Optional[int]]]:
        suffix = path.suffix.casefold()
        if suffix in {".txt", ".md", ".markdown", ".csv"}:
            return [(self._read_text(path), None)]

        if suffix == ".pdf":
            try:
                from langchain_community.document_loaders import PyPDFLoader

                pages = PyPDFLoader(str(path)).load()
                return [
                    (page.page_content or "", int(page.metadata.get("page", index)))
                    for index, page in enumerate(pages)
                ]
            except Exception as loader_error:
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(str(path))
                    return [
                        (page.extract_text() or "", index)
                        for index, page in enumerate(reader.pages)
                    ]
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"No se pudo leer el PDF ({loader_error}; alternativa: {fallback_error})"
                    ) from fallback_error

        if suffix in {".html", ".htm"}:
            parser = _TextoHTML()
            parser.feed(self._read_text(path))
            return [(html.unescape("\n".join(parser.partes)), None)]

        if suffix == ".docx":
            try:
                from docx import Document
                from docx.table import Table
                from docx.text.paragraph import Paragraph

                document = Document(str(path))
                content: list[tuple[str, Optional[int]]] = []
                recent_heading = ""
                body = document.element.body
                for element in body.iterchildren():
                    if element.tag.endswith("}p"):
                        paragraph = Paragraph(element, document).text.strip()
                        if paragraph:
                            content.append((paragraph, None))
                            recent_heading = paragraph
                    elif element.tag.endswith("}tbl"):
                        table = Table(element, document)
                        structured = self._format_schedule_table(table, recent_heading)
                        if structured:
                            content.append((structured, None))
                        else:
                            rows = [
                                " | ".join(cell.text.strip() for cell in row.cells)
                                for row in table.rows
                            ]
                            content.append(("\n".join(rows), None))
                return content
            except Exception as error:
                raise RuntimeError(f"No se pudo leer el DOCX: {error}") from error

        return []

    @staticmethod
    def _format_schedule_table(table, heading: str = "") -> str | None:
        """Convierte cuadrículas hora/día a evidencia legible con encabezados."""
        day_names = {
            "lunes": "lunes",
            "martes": "martes",
            "miercoles": "miércoles",
            "jueves": "jueves",
            "viernes": "viernes",
            "sabado": "sábado",
            "domingo": "domingo",
        }
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        header_index = None
        day_columns: list[tuple[int, str]] = []

        for row_index, row in enumerate(rows):
            matches = []
            for column_index, value in enumerate(row):
                normalized = _normalizar(value)
                day = next((name for key, name in day_names.items() if normalized == key), None)
                if day:
                    matches.append((column_index, day))
            if len(matches) >= 3:
                header_index = row_index
                day_columns = matches
                break

        if header_index is None:
            return None

        def parse_minutes(value: str) -> int | None:
            match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*", value)
            if not match:
                return None
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            if hour > 24 or minute > 59:
                return None
            return hour * 60 + minute

        # (día, actividad normalizada) -> (texto original, horas de inicio)
        events: dict[tuple[str, str], tuple[str, set[int]]] = {}
        for row in rows[header_index + 1:]:
            if not row:
                continue
            start = parse_minutes(row[0])
            if start is None:
                continue
            for column_index, day in day_columns:
                if column_index >= len(row):
                    continue
                cell_text = row[column_index].replace("\r", "\n")
                activities = []
                for line in cell_text.splitlines():
                    label = re.sub(r"\s+", " ", line).strip(" \t|;,")
                    if label and _normalizar(label) not in {_normalizar(x) for x in activities}:
                        activities.append(label)
                for label in activities:
                    key = (day, _normalizar(label))
                    if key not in events:
                        events[key] = (label, set())
                    events[key][1].add(start)

        if not events:
            return None

        day_order = {name: index for index, name in enumerate(day_names.values())}
        table_labels = []
        seen_labels = set()
        for row in rows[:header_index]:
            for value in row:
                label = re.sub(r"\s+", " ", value).strip()
                normalized = _normalizar(label)
                if normalized and normalized not in seen_labels:
                    seen_labels.add(normalized)
                    table_labels.append(label)
        context = "; ".join(part for part in [heading, *table_labels] if part.strip())

        def format_time(minutes: int) -> str:
            return f"{minutes // 60:02d}:{minutes % 60:02d}"

        lines = [f"Tabla de horarios; contexto: {context or 'sin título indicado'}." ]
        ordered_events = sorted(
            events.items(),
            key=lambda item: (day_order.get(item[0][0], 99), min(item[1][1]), item[1][0].casefold()),
        )
        for (day, _), (label, starts) in ordered_events:
            intervals = []
            sorted_starts = sorted(starts)
            interval_start = previous = sorted_starts[0]
            for current in sorted_starts[1:]:
                if current == previous + 60:
                    previous = current
                    continue
                intervals.append((interval_start, previous + 60))
                interval_start = previous = current
            intervals.append((interval_start, previous + 60))
            for start, end in intervals:
                lines.append(f"{day.capitalize()} {format_time(start)}–{format_time(end)}: {label}.")
        return "\n".join(lines)

    @staticmethod
    def _chunk_text(
        text: str,
        max_chars: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[str]:
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return []

        max_chars = max(200, int(max_chars))
        overlap = min(max(0, int(overlap)), max_chars // 3)
        chunks: list[str] = []

        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = re.sub(r"[ \t]+", " ", paragraph).strip()
            if not paragraph:
                continue
            start = 0
            while start < len(paragraph):
                end = min(start + max_chars, len(paragraph))
                if end < len(paragraph):
                    candidates = [
                        paragraph.rfind("\n", start, end),
                        paragraph.rfind(". ", start, end),
                        paragraph.rfind("; ", start, end),
                        paragraph.rfind(" ", start, end),
                    ]
                    cut = max(candidates)
                    if cut > start + max_chars // 2:
                        end = cut + (1 if paragraph[cut:cut + 2] in {". ", "; "} else 0)
                piece = paragraph[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end >= len(paragraph):
                    break
                start = max(start + 1, end - overlap)

        return chunks

    def load(self) -> dict:
        """Carga Documentos y prepara data/processed como respaldo permitido."""
        next_chunks: list[str] = []
        next_sources: list[str] = []
        next_tiers: list[str] = []
        next_files: list[str] = []
        next_errors: list[str] = []
        counts = {"dynamic": 0, "static": 0}
        source_roots = [("dynamic", self.ruta, "Documentos")]
        if self.static_root is not None:
            for category in self.static_categories:
                path = self.static_root / category
                if path.is_dir():
                    source_roots.append(("static", path, "data/processed"))

        for tier, root, source_prefix in source_roots:
            seen_in_tier: set[str] = set()
            for path in self._files_in(root):
                try:
                    pages = self._read_file(path)
                    category_root = root.name
                    relative_source = (
                        f"{source_prefix}/{category_root}/"
                        f"{path.relative_to(root).as_posix()}"
                    )
                    loaded_any_text = any(page_text.strip() for page_text, _ in pages)
                    for page_text, page_number in pages:
                        for chunk in self._chunk_text(page_text):
                            key = _normalizar(chunk)
                            if not key or key in seen_in_tier:
                                continue
                            seen_in_tier.add(key)
                            source = relative_source
                            if page_number is not None:
                                source += f" · pág. {page_number + 1}"
                            next_chunks.append(chunk)
                            next_sources.append(source)
                            next_tiers.append(tier)
                    if loaded_any_text:
                        next_files.append(relative_source)
                        counts[tier] += 1
                    else:
                        next_errors.append(f"{relative_source}: no contiene texto extraíble")
                except Exception as error:
                    next_errors.append(f"{path.name}: {type(error).__name__}: {error}")

        next_embeddings = None
        if self.model is not None and next_chunks:
            try:
                next_embeddings = self.model.encode(
                    next_chunks,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            except Exception as error:
                next_errors.append(f"Embeddings locales no disponibles: {error}")

        with self._lock:
            self.chunks = next_chunks
            self.chunk_sources = next_sources
            self.chunk_tiers = next_tiers
            self.embeddings = next_embeddings
            self.files_loaded = next_files
            self.load_errors = next_errors
            self.document_count = len(next_files)
            self.dynamic_document_count = counts["dynamic"]
            self.static_document_count = counts["static"]

        for error in next_errors:
            print(f"[AGENT:{self.nombre}] Aviso: {error}")
        print(
            f"[AGENT:{self.nombre}] {self.document_count} archivos y "
            f"{len(next_chunks)} fragmentos cargados desde {self.ruta}"
        )
        return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "categoria": self.nombre,
                "ruta": str(self.ruta),
                "archivos": self.document_count,
                "archivos_dinamicos": self.dynamic_document_count,
                "archivos_estaticos_respaldo": self.static_document_count,
                "fragmentos": len(self.chunks),
                "archivos_cargados": list(self.files_loaded),
                "errores": list(self.load_errors),
            }

    def file_signature(self) -> tuple[tuple[str, int, int], ...]:
        """Huella barata de archivos para detectar cambios hechos por el panel."""
        signature = []
        roots = [("Documentos", self.ruta)]
        if self.static_root is not None:
            roots.extend(
                ("data/processed", self.static_root / category)
                for category in self.static_categories
            )
        for label, root in roots:
            for path in self._files_in(root):
                try:
                    stat = path.stat()
                    relative = f"{label}/{root.name}/{path.relative_to(root).as_posix()}"
                    signature.append((relative, stat.st_size, stat.st_mtime_ns))
                except OSError:
                    continue
        return tuple(signature)

    @property
    def category_preview(self) -> str:
        with self._lock:
            return " ".join(self.chunks[:3])[:1800]

    def search_with_source(
        self,
        query: str,
        top_k: int = 4,
        threshold: float = 0.16,
        must_contain: Optional[list[str]] = None,
    ) -> list[dict]:
        with self._lock:
            chunks = list(self.chunks)
            sources = list(self.chunk_sources)
            tiers = list(self.chunk_tiers)
            embeddings = self.embeddings

        if not chunks or top_k <= 0:
            return []

        query_norm = _normalizar(query)
        query_tokens = [
            token for token in _tokens(query)
            if len(token) > 1 and token not in {
                "que", "como", "cuando", "donde", "quien", "cual", "para",
                "por", "con", "del", "las", "los", "una", "unos", "unas",
                "hay", "puedes", "podrias", "decime", "dime", "necesito",
                "quiero", "saber", "materia", "asignatura",
            }
        ]
        aliases = [_normalizar(alias) for alias in (must_contain or []) if alias.strip()]
        lexical_scores: list[float] = []

        for chunk, source in zip(chunks, sources):
            searchable = _normalizar(f"{chunk} {source}")
            if aliases and not any(
                re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", searchable)
                for alias in aliases
            ):
                lexical_scores.append(-1.0)
                continue

            score = 0.0
            if len(query_norm) > 3 and query_norm in searchable:
                score += 5.0
            present = set(_tokens(searchable))
            for token in set(query_tokens):
                if token in present:
                    score += 2.0 if len(token) >= 5 else 1.0
            # Códigos cortos como MDL1, I1 o PP son términos muy distintivos.
            for token in set(query_tokens):
                if re.search(r"\d", token) and token in present:
                    score += 4.0
            lexical_scores.append(score)

        scores = lexical_scores
        if (
            self.model is not None
            and embeddings is not None
            and np is not None
            and any(score >= 0 for score in lexical_scores)
        ):
            try:
                query_embedding = self.model.encode([query], convert_to_numpy=True)
                vectors = np.asarray(embeddings)
                query_vector = np.asarray(query_embedding).reshape(-1)
                denominators = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vector) + 1e-8
                similarities = (np.dot(vectors, query_vector) / denominators).tolist()
                scores = [
                    -1.0 if lexical < 0 else max(lexical, float(similarity) * 5.0)
                    for lexical, similarity in zip(lexical_scores, similarities)
                ]
            except Exception as error:
                print(f"[AGENT:{self.nombre}] Falló búsqueda vectorial; uso texto: {error}")
                scores = lexical_scores

        def collect(indices: list[int]) -> list[dict]:
            ranking = sorted(((index, scores[index]) for index in indices), key=lambda item: item[1], reverse=True)
            results: list[dict] = []
            for index, score in ranking:
                if score <= 0:
                    continue
                if (
                    self.model is not None
                    and embeddings is not None
                    and lexical_scores[index] == 0
                    and score < threshold
                ):
                    continue
                results.append({
                    "chunk": chunks[index],
                    "fuente": sources[index],
                    "score": float(score),
                    "categoria": self.nombre,
                    "tipo_fuente": tiers[index],
                })
                if len(results) >= top_k:
                    break
            return results

        dynamic_results = collect([i for i, tier in enumerate(tiers) if tier == "dynamic"])
        if dynamic_results:
            return dynamic_results
        return collect([i for i, tier in enumerate(tiers) if tier == "static"])

    def search(self, query: str, top_k: int = 5, threshold: float = 0.22):
        """Contrato compatible con versiones anteriores: (fragmento, puntaje)."""
        return [
            (item["chunk"], item["score"])
            for item in self.search_with_source(query, top_k=top_k, threshold=threshold)
        ]

