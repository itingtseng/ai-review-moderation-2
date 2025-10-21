# 🛡️ AI Review Moderation 2.0 (RAG + LLM)

A lightweight end‑to‑end demo for AI-powered review moderation using **semantic retrieval (FAISS + sentence-transformers)** and **LLM reasoning** to produce a flag/not‑flag decision **with human‑readable explanations** and **similar cases**.

## 🔧 Tech Stack
- Backend: FastAPI, sentence-transformers, FAISS, OpenAI API (or Anthropic)
- Frontend: Streamlit
- Orchestration: simple RAG pattern (retrieval → LLM classification)
- Docs: PRD, Model Card

## 🗂 Project Structure
```
backend/
  app.py
  retriever.py
  classifier.py
  requirements.txt
  .env.example
  data/
    reviews_train.csv       # put your labeled reviews here (id,text,label)
    reviews_eval.csv        # evaluation split (id,text,label)
    faiss.index             # built by retriever
    embeddings.npy          # built by retriever
    meta.json               # built by retriever
frontend/
  streamlit_app.py
docs/
  PRD.md
  model_card.md
```

## 🚀 Quick Start

### 1) Create & activate venv (Python 3.10+)
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2) Prepare environment
Copy `.env.example` to `.env` and set your keys:
```
OPENAI_API_KEY=sk-...
MODEL=gpt-4o-mini
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
TOP_K=5
```

### 3) Build vector index (first-time)
```bash
python -c "from backend.retriever import build_index; build_index()"
```

### 4) Run backend
```bash
uvicorn backend.app:app --reload --port 8010
```

### 5) Run frontend
```bash
streamlit run frontend/streamlit_app.py
```

## 📈 Evaluation
See `docs/model_card.md` for metrics. A simple script can compute precision/recall/F1 on `reviews_eval.csv`.

## 🧩 Notes
- Replace OpenAI with your preferred LLM provider if needed.
- For production, add authentication, rate limiting, and logging.
