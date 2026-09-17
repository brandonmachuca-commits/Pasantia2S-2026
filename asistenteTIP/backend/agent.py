import re
import numpy as np

from pathlib import Path
from typing import List, Tuple, Optional


class Agent:

    def __init__(self, nombre: str, carpeta: str, model):
        self.nombre = nombre
        self.carpeta = carpeta
        self.model = model

        self.tipo_busqueda = (
            "semantico"
            if nombre == "cursos"
            else "keywords"
        )

        self.chunks: List[str] = []
        self.embeddings: Optional[np.ndarray] = None

        self.load()

    # ─────────────────────────────────────────────

    def load(self):
        data_path = (
            Path(__file__).parent.parent
            / "backend"
            / "data"
            / "processed"
        )

        archivo = (
            data_path
            / self.carpeta
            / "contenido.txt"
        )

        print("\n===================================")
        print(f"[AGENT] {self.nombre}")
        print(f"[AGENT] Archivo: {archivo.resolve()}")
        print("===================================\n")

        if not archivo.exists():
            print(f"[AGENT] ERROR: No existe {archivo}")
            return

        with open(archivo, "r", encoding="utf-8") as f:
            texto = f.read()

        print(f"[AGENT] {self.nombre}: {len(texto)} caracteres")
        print(f"[AGENT] {self.nombre}: {texto.count(chr(10))} líneas")

        # chunking
        self.chunks = self._chunk_text(texto)

        print(f"[AGENT] {self.nombre}: {len(self.chunks)} chunks")

        if not self.chunks:
            print("[AGENT] WARNING: No se generaron chunks")
            return

        # debug
        print("\n[AGENT] Primeros chunks:\n")
        for i, chunk in enumerate(self.chunks[:3]):
            print(f"--- CHUNK {i+1} ---")
            print(chunk[:400])
            print()

        # embeddings solo si es semántico
        if self.model and self.tipo_busqueda == "semantico":
            try:
                self.embeddings = self.model.encode(
                    self.chunks,
                    convert_to_numpy=True
                )
                print(f"[AGENT] {self.nombre}: embeddings generados")
            except Exception as e:
                print(f"[AGENT] ERROR embeddings: {e}")
                self.embeddings = None

    # ─────────────────────────────────────────────

    def _chunk_text(
        self,
        text: str,
        max_chars: int = 700,
        overlap: int = 120
    ) -> List[str]:

        text = text.replace("\r", "")

        bloques = re.split(
            r"(?:={10,}|-{10,}|\n\s*\n)",
            text
        )

        chunks = []

        for bloque in bloques:
            bloque = bloque.strip()

            if len(bloque) < 20:
                continue

            if len(bloque) <= max_chars:
                chunks.append(bloque)
                continue

            inicio = 0
            while inicio < len(bloque):
                fin = inicio + max_chars

                if fin < len(bloque):
                    corte = bloque.rfind("\n", inicio, fin)
                    if corte != -1:
                        fin = corte

                chunk = bloque[inicio:fin].strip()
                if len(chunk) > 20:
                    chunks.append(chunk)

                inicio = fin - overlap

        return chunks

    # ─────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.22
    ) -> List[Tuple[str, float]]:

        print(f"[SEARCH] Query: {query}")

        if not self.chunks:
            return []

        # BÚSQUEDA POR KEYWORDS

        if self.tipo_busqueda == "keywords":
            print("[SEARCH] usando búsqueda por keywords")

            resultados = []

            query_clean = re.sub(
                r"[^\w\s]",
                "",
                query.lower()
            )

            palabras = query_clean.split()
            
            STOPWORDS = {"las", "los", "una", "uno", "del", "que", "como", "cual",
                     "cuales", "para", "por", "con", "sus", "mis", "hay", "son",
                     "este", "esta", "estos", "estas", "cuando", "donde", "quien"}

             # Solo palabras de más de 2 letras y que no sean stopwords
            palabras_filtradas = [p for p in palabras if len(p) > 2 and p not in STOPWORDS] 

            print(f'[SEARCH] palabras filtradas: {palabras_filtradas}')

            # if (
            #     self.nombre == "parciales"
            #     and "parcial" in query_clean
            #     and "semestre" not in query_clean
            # ):

            #     resultados = []

            #     for chunk in self.chunks:
            #         if "semestre" in chunk.lower():
            #             resultados.append((chunk, 1000))

            #     if resultados:
            #         print("[SEARCH] consulta general de parciales")
            #         return resultados[:top_k]

            # ------------------------------------------
            # 2. Buscar meses
            # ------------------------------------------
            meses = [
                "enero", "febrero", "marzo", "abril",
                "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre",
                "noviembre", "diciembre"
            ]

            for mes in meses:
                if mes in query_clean:
                    resultados = []
                    for chunk in self.chunks:
                        if mes in chunk.lower():
                            resultados.append((chunk, 1000))
                    if resultados:
                        print("[SEARCH] match por mes")
                        return resultados[:top_k]


            # ------------------------------------------
            # 1. Buscar siglas exactas
            # ------------------------------------------
            siglas = [
                s for s in re.findall(
                    r"\b[A-Z0-9]{2,6}\b",
                    query.upper()
                )
                if len(s) <= 6 and s.lower() not in STOPWORDS
            ]   
            

            if siglas:
                for chunk in self.chunks:
                    texto = chunk.upper()
                    score = 0
                    for sigla in siglas:
                        if re.search(
                            rf"\b{re.escape(sigla)}\b",
                            texto
                        ):
                            score += 1000
                    if score > 0:
                        resultados.append((chunk, score))

                if resultados:
                    print("[SEARCH] match por siglas")
                    return resultados[:top_k]

           

            # ------------------------------------------
            # 3. Keywords
            # ------------------------------------------
            for chunk in self.chunks:
                texto = chunk.lower()
                score = 0

                if query_clean in texto:
                    score += 100

                for palabra in palabras_filtradas:
                    # if len(palabra) <= 2:
                    #     continue
                    if palabra in texto:
                        score += 10

                if score > 0:
                    resultados.append((chunk, float(score)))

            resultados.sort(
                key=lambda x: x[1],
                reverse=True
            )

            print(f"[SEARCH] resultados: {len(resultados)}")
            return resultados[:top_k]

        # BÚSQUEDA SEMÁNTICA

        print("[SEARCH] usando embeddings")

        if self.embeddings is None:
            return []

        try:
            q_emb = self.model.encode(
                [query],
                convert_to_numpy=True
            )

            emb_norm = np.linalg.norm(
                self.embeddings,
                axis=1
            )
            q_norm = np.linalg.norm(q_emb)

            sims = (
                np.dot(self.embeddings, q_emb.T).flatten()
                / (emb_norm * q_norm + 1e-8)
            )

            top = np.argsort(sims)[::-1][:top_k]

            resultados = []

            for i in top:
                score = float(sims[i])
                print(f"[SEARCH] score={score:.3f}")
                if score >= threshold:
                    resultados.append(
                        (
                            self.chunks[i],
                            score
                        )
                    )

            return resultados

        except Exception as e:
            print(f"[SEARCH] ERROR: {e}")
            return []