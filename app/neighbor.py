# app/neighbor.py
import os
import numpy as np
import pandas as pd
import faiss  # pip install faiss-cpu
from typing import List, Tuple
from sentence_transformers import SentenceTransformer

DEFAULT_DATA = "data/raw/_SELECT_A_object_id_A_complex_id_A_vote_reason_id_B_reason_A_dat_202110291714.csv"
TEXT_COL = "review_text"

class NeighborIndex:
    def __init__(self, data_path: str = DEFAULT_DATA, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.data_path = data_path
        self.model = SentenceTransformer(model_name)
        self.df = None
        self.index = None
        self.emb = None

    def load_data(self):
        df = pd.read_csv(self.data_path)
        df[TEXT_COL] = df[TEXT_COL].fillna("").astype(str)
        # 你可在這裡挑出只需審核的 reason 範圍；此處保留原始（show case 比較多樣）
        self.df = df.reset_index(drop=True)

    def build(self, normalize=True, batch_size=256):
        if self.df is None:
            self.load_data()
        texts = self.df[TEXT_COL].tolist()
        emb = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=normalize)
        emb = emb.astype("float32")
        index = faiss.IndexFlatIP(emb.shape[1])  # 內積 = 餘弦（已正規化）
        index.add(emb)
        self.index = index
        self.emb = emb

    def search(self, query: str, k: int = 5, normalize=True) -> Tuple[float, List[Tuple[float, int]]]:
        if self.index is None:
            self.build()
        qv = self.model.encode([query], normalize_embeddings=normalize).astype("float32")
        sims, idxs = self.index.search(qv, k)
        sims = sims[0]; idxs = idxs[0]
        # 將平均相似度映射到 0~1（門檻可調）
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
