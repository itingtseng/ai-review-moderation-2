# app/neighbor.py
import os
from pathlib import Path
import numpy as np
import pandas as pd
import faiss  # pip install faiss-cpu
from typing import List, Tuple
from sentence_transformers import SentenceTransformer

TEXT_COL = "review_text"

# 預設候選路徑（依序嘗試）
CANDIDATE_PATHS = [
    os.getenv("DATA_PATH", "").strip(),  # 可用環境變數/Secrets 覆蓋
    "data/raw/_SELECT_A_object_id_A_complex_id_A_vote_reason_id_B_reason_A_dat_202110291714",
    "data/samples/sample_reviews.csv",   # ← 雲端 fallback
]

class NeighborIndex:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.df = None
        self.index = None

    def _resolve_data_path(self) -> str:
        for p in CANDIDATE_PATHS:
            if p and Path(p).exists():
                return p
        raise FileNotFoundError(
            "找不到資料檔。請上傳原始資料到 repo，或提供 data/samples/sample_reviews.csv，"
            "也可在環境變數/Secrets 設定 DATA_PATH 指向檔案。"
        )

    def load_data(self):
        path = self._resolve_data_path()
        df = pd.read_csv(path)
        if TEXT_COL not in df.columns:
            raise ValueError(f"資料缺少欄位 `{TEXT_COL}`，目前欄位有：{list(df.columns)}")
        df[TEXT_COL] = df[TEXT_COL].fillna("").astype(str)
        self.df = df.reset_index(drop=True)

    def build(self, normalize=True, batch_size=256):
        if self.df is None:
            self.load_data()
        texts = self.df[TEXT_COL].tolist()
        model = self.model
        emb = model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=normalize)
        emb = np.asarray(emb, dtype="float32")
        index = faiss.IndexFlatIP(emb.shape[1])  # 內積（若已 normalize ≈ cosine）
        index.add(emb)
        self.index = index

    def search(self, query: str, k: int = 5, normalize=True) -> Tuple[float, List[Tuple[float, int]]]:
        if self.index is None:
            self.build()
        qv = self.model.encode([query], normalize_embeddings=normalize).astype("float32")
        sims, idxs = self.index.search(qv, k)
        sims = sims[0]; idxs = idxs[0]
        # 平均相似度映射到 0~1（可調整校準）
        s = float(np.mean(sims))
        conf = (s - 0.25) / (0.85 - 0.25)
        conf = max(0.0, min(1.0, conf))
        return conf, [(float(sim), int(i)) for sim, i in zip(sims, idxs)]

# 簡易單例
_neighbor_singleton = None
def get_index() -> NeighborIndex:
    global _neighbor_singleton
    if _neighbor_singleton is None:
        _neighbor_singleton = NeighborIndex()
        _neighbor_singleton.load_data()
        _neighbor_singleton.build()
    return _neighbor_singleton
