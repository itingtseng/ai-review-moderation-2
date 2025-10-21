# Model Card — AI Review Moderation 2.0

## Model Details
- Task: Review moderation (binary: flag / not_flag) with LLM reasoning
- Architecture: RAG (FAISS + sentence-transformers) + LLM JSON output

## Intended Use
- Pre‑screen user reviews/comments for policy violations; human‑in‑the‑loop required.

## Data
- Labeled dataset with fields: id, text, label. Describe collection/labeling process.

## Metrics
- Offline: Precision/Recall/F1 on held‑out eval set
- Human agreement: agreement rate on sampled borderline cases

## Risks & Limitations
- Potential bias against certain dialects or groups.
- Hallucinations → mitigated via JSON schema + retrieval context + abstain policy.

## Maintenance
- Regular re‑indexing and periodic re‑evaluation.
