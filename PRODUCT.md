# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary framing: trust & safety moderators working a queue of user reviews. They need to decide quickly and defensibly whether to Approve, Flag or Escalate each one, and to see why the system thinks a review is risky.

Actual audience today: people evaluating the prototype (hiring managers, interviewers, stakeholders) who open the live Streamlit link. Within minutes they have to grasp the explainable-moderation idea and trust that its claims are honest.

Design for the moderator, and make sure an evaluator can read it. Neither audience should have to sacrifice what it needs for the other.

## Product Purpose

Verdict AI is an explainable review-moderation and human-review workflow prototype. It combines deterministic policy rules (keywords, phrases and regex, with weights kept in `app/rules.yml`) with semantic similar-case retrieval (SentenceTransformer `all-MiniLM-L6-v2` + FAISS). From these it produces a heuristic Low / Medium / High risk tier and shows the evidence behind it.

The PRD's stated goal is to shorten how long harmful reviews (hate, harassment, PII, spam/advertising) stay exposed and to save moderator time. Success means a moderator can see the highest-risk items first, along with similar cases and short reasons, and make a decision that can be traced back to its evidence.

## Positioning

Explainable, not a black box. Every result shows the policy signals, matched phrases and patterns, rule weights and retrieved similar cases behind its tier. The primary result needs no LLM: it is rules plus semantic similar-case retrieval. Describe it that way, not as a full RAG or agent system.

## Operating Context

- Workflow: analyze a review → inspect evidence cards and the risk tier → record a moderator decision (Flag, Escalate, Approve, Retry) → move on to the next pending review in the queue.
- App areas: Review Moderation, Moderation Queue (tabs: All / Passed / Flagged / Escalated, grouped by the risk tier computed live), Analytics, Settings (risk thresholds).
- Moderator actions live only in Streamlit session state and are not saved.
- Deployed on Streamlit Community Cloud; run locally with `streamlit run streamlit_app.py`.

## Capabilities and Constraints

- **Stack is fixed:** Streamlit with injected CSS. Do not rewrite it in another framework.
- **English-only UI**, even though `docs/PRD.md` is written in Chinese.
- Nine policy categories (Wrong Community, Off-topic, False Information, Affiliated with Community, Competitor / Ex-employee, Toxic / Hate / Lewd, Privacy / PII, Promotion / Advertising, COVID-related). Some of them cannot be verified from text alone and need human judgment.
- Tier thresholds: High ≥ 0.70, Medium ≥ 0.40, Low < 0.40. These are heuristic and uncalibrated.
- Degraded mode: when retrieval is unavailable, the app keeps working on rule evidence alone.
- The experimental FastAPI/OpenAI backend (`backend/`, `frontend/`) is not connected to the primary app.

## Brand Commitments

- The name **Verdict AI** (with the 🛡️ shield used in the README) is the fixed identity.
- Voice: precise and candid about limitations. Never overstate what the system knows.

## Evidence on Hand

- `data/samples/sample_reviews.csv`: 20 illustrative reviews used for demo retrieval. They are not a representative or verified set.
- Queue, analytics, historical-outcome and moderator metadata are **synthetic**. Similar-case cards deliberately show no past decision or risk tier; their policy category is an unverified sample annotation.
- No validated accuracy, precision, recall, F1, latency or retrieval-quality results exist. Do not fabricate metrics, customers, testimonials or production claims.
- The original source corpus was removed for provenance reasons. Do not restore it.

## Product Principles

1. **Show the evidence, not just the verdict.** Every risk tier should trace back to visible rules, matches and similar cases.
2. **Honesty caveats are part of the product.** Always make it clear that scores are heuristic, not probabilities, and that demo data is synthetic. Integrate these notes cleanly and never hide them.
3. **The human decides.** The system ranks and explains; moderator actions are the authoritative outcome.
4. **Speed to a defensible decision.** Highest-risk items first, scannable evidence, one obvious next action.
5. **Legible to a newcomer.** An evaluator who has never moderated should be able to follow the flow without help.

## Accessibility & Inclusion

Target WCAG 2.2 AA: meet contrast minimums, support keyboard operation, and never signal a risk tier or decision state by color alone; pair it with text, an icon or a position.
