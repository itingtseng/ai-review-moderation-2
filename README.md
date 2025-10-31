# 🛡️ AI Review Moderation 2.0  
**Explainable Trust & Safety Moderation (Rules + Lexicons + Semantic Neighbors)**

A lightweight, end-to-end demo for **review moderation** that combines:

✅ Rule-based scoring  
✅ Lexicon phrase matching  
✅ Regex pattern detection (URL / email / phone / PII)  
✅ Semantic similarity (vector neighbors)  
✅ Explainable risk cards  
✅ Human-in-the-loop routing (HITL)  

The system produces **flag/not-flag** decisions with:
- Human-readable explanations
- Triggered rules
- Matching phrases
- Similar past cases (when available)

---

## 🏛 Architecture Overview

   User Text
      ↓
Text Preprocessing
      ↓
Phrase / Rule Matching  (weighted α)
      ↓
Semantic Neighbors     (weighted β)
      ↓
Score Blending (α·rules + β·neighbors)
      ↓
Decision Tiering (LOW / MEDIUM / HIGH)
      ↓
Explainability Cards


When full historical data is available, semantic neighbors boost signal quality.  
When data is restricted (privacy), the engine **gracefully degrades** into rule-only mode.

---

## 🔧 Tech Stack

- **Frontend**: Streamlit
- **Reasoning Engine**: Python + lexicon scoring
- **Semantic Retrieval**: sentence-transformers + FAISS (optional)
- **Rules / Lexicons**: YAML (auditable, editable)
- **Documentation**: PRD, Model Card

(No raw data is included due to privacy constraints; see Degradation Modes below.)

---

## 🗂 Project Structure

app/
  decision.py          # core scoring engine
  neighbor.py          # FAISS wrapper + fallback
  rules.yml            # curated rules/lexicons
  rules_generated.yml  # auto-expanded lexicons
  sample_reviews.csv   # small public sample corpus (optional)
streamlit_app.py       # demo UI
docs/
  PRD.md
  model_card.md
notebooks/
  01_exploratory_iteration.ipynb
  02_rule_mining.ipynb
  03_lexicon_growth.ipynb

---

## 🚀 Quick Start

### 1) Environment
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run UI
```bash
streamlit run streamlit_app.py
```

---


## 📥 Data Requirements

### Optional
`sample_reviews.csv`

Used to build a tiny semantic index for neighbor scoring.

Replace with:
```bash
id,text,vote_reason_id
```
> Raw enterprise data is **not** included in this repo due to privacy.

---

## 🧠 Graceful Degradation (Important!)

This system supports **privacy-aware downgrade modes**:

| Mode    | What’s Available         | Behavior                                      |
|---------|--------------------------|-----------------------------------------------|
| Full    | Raw historical corpus    | Rules + Lexicons + Semantic Neighbors         |
| Mid     | sample_reviews.csv only  | Local semantic similarity                     |
| Minimal | No corpus                | Pure rules engine (still explainable!)        |

High-signal categories remain stable:

- Promotion / Advertising
- Toxic / Harassment
- Privacy / PII
- COVID misinformation

Ambiguous categories (e.g., Off-topic) route to HITL (Human-In-The-Loop).

---

## 🔍 Explainability Cards

For every decision, the UI shows:

- Category risk
- Extracted phrases
- Lexicon matches
- Regex hits (URL/email/phone)
- Neighbor evidence (when available)
- Final blended score

This makes decisions **auditable** and **transparent**.

---

## 🧩 Categories Covered

| vote_reason_id | Category               | Auto-manageable?                               |
|----------------|------------------------|------------------------------------------------|
| 2              | Off-topic              | ✅ (weak signal → relies on neighbors)         |
| 6              | Toxic / Hate / Lewd    | ✅                                             |
| 7              | Privacy / PII          | ✅                                             |
| 8              | Promotional content    | ✅                                             |
| 9              | COVID / misinformation | ✅                                             |

Other flag types are intentionally **excluded** (not machine-verifiable).

---

## 📈 Evaluation

See `docs/model_card.md` for:

- precision / recall / F1
- false positive analysis
- category-wise breakdown

---

## 🧪 Lexicon Growth (Auto-Mining)

Notebooks mine phrases using:

- log-odds ratio enrichment
- multi-gram extraction
- class-conditional frequency
- typo clustering

The engine expands:
```bash
rules_lexicons.yml
rules_generated.yml
```

These can be manually audited.

---

## 👁‍🗨 Human-In-The-Loop (HITL)

Ambiguous scores route to human review:

- Score thresholding
- Confidence display
- Neighbor examples

This mimics real Trust & Safety queues.

---

## 🔐 Privacy Notes

- Raw enterprise datasets are not stored in this repo
- Only synthetic/public sample CSV is included
- Model degradation preserves explainability

---

## 🧯 Risk / Failure Modes

- Off-topic ambiguity without semantic evidence
- Novel promotion tactics unseen in lexicon
- Evasive toxic slang evolution

Documented in the Model Card.

---

## 🛠 For Production

Add:

- Rate limiting
- AuthN/AuthZ
- Moderation queues
- Feedback loops
- Bias audits

---

## 👀 Why This Matters (Pitch)

This repo demonstrates:

- Explainable moderation
- Auditable YAML rules
- Semantic retrieval (optional)
- Privacy-aware degradation
- Human-review queue routing
- Safe fallback behavior

Perfect for Meta / TikTok / YouTube Trust & Safety roles.

---

## 🧳 Deployment

Works on:

- Local
- Streamlit Cloud
- GitHub Codespaces

`sample_reviews.csv` enables cloud mode without private data.

---

## 🏁 Status

✅ Rule engine complete  
✅ Lexicon auto-growth complete  
✅ Explainability UI complete  
✅ Degradation mode implemented  
⬜ (Optional) raw corpus FAISS index  
⬜ (Optional) admin review queue  

Even without raw embeddings, this is a shippable demo.

---

## 📜 License

MIT.  
Rules and lexicons are auditable and editable.


