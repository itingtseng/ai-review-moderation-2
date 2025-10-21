# backend/retriever.py
import json
import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path

EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DATA_DIR = Path(__file__).parent / "data"
INDEX_PATH = DATA_DIR / "faiss.index"
EMB_PATH = DATA_DIR / "embeddings.npy"
META_PATH = DATA_DIR / "meta.json"
TRAIN_CSV = DATA_DIR / "reviews_train.csv"

def build_index(csv_path=str(TRAIN_CSV)):
    df = pd.read_csv(csv_path)
    assert {"id","text","label"}.issubset(df.columns), "CSV must have id,text,label"
    texts = df["text"].astype(str).tolist()

    model = SentenceTransformer(EMB_MODEL)
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    embs = embs.astype("float32")
    index = faiss.IndexFlatIP(embs.shape[1])
    index.add(embs)

    faiss.write_index(index, str(INDEX_PATH))
    np.save(EMB_PATH, embs)

    meta = [{"id": int(df.iloc[i]["id"]), "text": texts[i], "label": str(df.iloc[i]["label"])} for i in range(len(df))]
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

def retrieve_similar(query_text: str, top_k: int = 5):
    model = SentenceTransformer(EMB_MODEL)
    q = model.encode([query_text], normalize_embeddings=True).astype("float32")

    index = faiss.read_index(str(INDEX_PATH))
    D, I = index.search(q, top_k)

    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    hits = []
    for score, idx in zip(D[0], I[0]):
        rec = meta[int(idx)]
        hits.append({"id": rec["id"], "text": rec["text"], "label": rec["label"], "score": float(score)})
    return hits
