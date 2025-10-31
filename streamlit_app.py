# streamlit_app.py
# ------------------------------------------------------------
# Flag Review 2.0 — Meta Trust & Safety + Moderator Queue
# - Hybrid scoring (rules + semantic neighbors)
# - Automatic fallback when neighbor data is unavailable (rule-only)
# - Parameters adjustable from Sidebar
# ------------------------------------------------------------

import streamlit as st
from typing import List, Tuple

# Internal modules
from app.decision import RuleEngine
from app.neighbor import get_index  # may fail on cloud (handled by try/except)

st.set_page_config(
    page_title="Flag Review 2.0 — Meta T&S + Moderator Queue",
    layout="wide",
)

# =========================
# Sidebar: Tunable Parameters
# =========================
st.sidebar.header("🛠️ Moderation Parameters")
alpha = st.sidebar.slider("Rule Weight α", 0.0, 1.0, 0.60, 0.05)
high_cut = st.sidebar.slider("HIGH Threshold", 0.50, 0.90, 0.70, 0.01)
med_cut = st.sidebar.slider("MEDIUM Threshold", 0.20, 0.80, 0.40, 0.01)
strong_boost = st.sidebar.checkbox("Boost rule score to 1.0 when strong evidence (regex) is detected", value=True)
topk = st.sidebar.slider("Neighbor Top-K", 3, 15, 5, 1)

st.sidebar.caption(
    "Tips:\n"
    "- Promotion/Privacy/Toxic/COVID → high-signal rules\n"
    "- Off-topic → relies more on semantic neighbors + HITL"
)

# =========================
# Initialize Rule Engine
# =========================
engine = RuleEngine(rules_file="app/rules.yml", alpha=alpha)

# =========================
# Attempt to load semantic index (FAISS)
# Fallback to rule-only mode if unavailable
# =========================
nbr = None
data_ok = True
err_msg = ""
try:
    nbr = get_index()
except Exception as e:
    data_ok = False
    err_msg = str(e)

# Show fallback notice (only if index fails)
if not data_ok:
    st.warning(
        "⚠️ Semantic neighbor data was not loaded.\n\n"
        "- System has switched to rule-only mode (neighbor_conf = 0).\n\n"
        "To enable neighbor search:\n"
        "  1) Upload raw review data to `data/raw/...`, or\n"
        "  2) Add a public sample file `data/samples/sample_reviews.csv`, or\n"
        "  3) Set a `DATA_PATH` environment variable in deployment settings.\n\n"
        f"Details: {err_msg}"
    )

# =========================
# Layout
# =========================
left, right = st.columns([0.60, 0.40])

# =========================
# Utility: Risk Tiering
# =========================
def apply_thresholds(final_score: float, high: float, med: float) -> str:
    if final_score >= high:
        return "HIGH"
    if final_score >= med:
        return "MEDIUM"
    return "LOW"

# =========================
# Utility: Boost strong evidence (regex)
# =========================
def upgrade_on_strong_evidence(per_rule: List[dict]) -> bool:
    """
    per_rule example:
    [
      {"reason_label": "...", "weight": 0.7, "score": 0.3,
       "regex_hits": [...], "keyword_hits": [...], "explanation": "..."},
      ...
    ]

    If regex_hits are present (URL/email/phone/PII/toxic terms),
    we treat that rule as high-confidence.
    """
    changed = False
    for r in per_rule:
        if r.get("regex_hits"):
            if r.get("score", 0) < 1.0:
                r["score"] = 1.0
                changed = True
    return changed

# =========================
# Left side — input + decision (Meta T&S card)
# =========================
with left:
    st.title("Flag Review 2.0")
    st.caption("Meta-style Trust & Safety + Moderator Queue (Hybrid Scoring)")

    user_text = st.text_area(
        "Paste a review to evaluate:",
        height=160,
        placeholder="e.g., Limited time! Apply now and schedule a tour. Visit our website or call now."
    )

    run_btn = st.button("Run Moderation", type="primary", use_container_width=True)

    if run_btn:
        if not user_text.strip():
            st.warning("Please enter text before running moderation.")
        else:
            # 1) Semantic similarity (if index available)
            if nbr is not None:
                neighbor_conf, neighbors = nbr.search(user_text, k=topk)
            else:
                neighbor_conf, neighbors = 0.0, []

            # 2) Rule scoring
            result = engine.decide(user_text, neighbor_conf=neighbor_conf)

            # 3) Boost strong evidence (regex)
            if strong_boost:
                if upgrade_on_strong_evidence(result.get("rules_detail", [])):
                    rule_score = sum(r.get("score", 0) for r in result["rules_detail"])
                    rule_score = min(rule_score, 1.0)
                    final_score = engine.alpha * rule_score + engine.beta * neighbor_conf
                    result["rule_score"] = round(rule_score, 3)
                    result["final_score"] = round(final_score, 3)

            # 4) Assign risk tier
            risk = apply_thresholds(result["final_score"], high_cut, med_cut)
            color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}[risk]

            # === Meta T&S decision card ===
            st.markdown(
                f"### ✅ Moderation Result: <span style='color:{color}'><b>{risk}</b></span>",
                unsafe_allow_html=True,
            )
            st.write(
                f"**final** = {result['final_score']}  |  "
                f"**rule** = {result['rule_score']}  |  "
                f"**neighbor** = {round(neighbor_conf, 3)}"
            )
            st.caption(
                f"α (rules) = {result['alpha']} / β (neighbors) = {result['beta']} ｜ "
                f"HIGH ≥ {high_cut} / MED ≥ {med_cut}"
            )

            # === Likely Reasons (Top 3) ===
            st.subheader("Likely Reasons (Top 3)")
            likely = result.get("likely_reasons", [])
            if not likely:
                st.write("- No rules triggered")
            else:
                for r in likely:
                    st.write(f"- **{r['reason_label']}** 〔score={r['score']}〕")

            # === Evidence Card ===
            st.subheader("Evidence (Explainability)")
            for r in result.get("rules_detail", []):
                if r.get("score", 0) <= 0:
                    continue
                with st.expander(f"{r['reason_label']} (w={r['weight']} → {r['score']})"):
                    if r.get("keyword_hits"):
                        st.write("**Keyword hits:**", ", ".join(r["keyword_hits"]))
                    if r.get("regex_hits"):
                        st.write("**Regex hits:** URL / phone / email / ads / PII / COVID / profanity")
                    if r.get("explanation"):
                        st.caption(r["explanation"])

            # === Populate Moderator Queue (if neighbors available) ===
            st.session_state["queue"] = []
            for sim, idx in neighbors:
                row = nbr.df.iloc[idx] if nbr is not None else {}
                st.session_state["queue"].append({
                    "idx": int(idx),
                    "similarity": round(float(sim), 3),
                    "text": row.get("review_text", ""),
                    "vote_reason_id": int(row.get("vote_reason_id", -1)) if "vote_reason_id" in row else -1,
                })

            if neighbors:
                st.success("Moderator Queue updated (Top-K similar cases).")
            elif nbr is None:
                st.info("Rule-only mode: No semantic neighbors available.")

# =========================
# Right side — Moderator Queue (Product demo)
# =========================
with right:
    st.header("Moderator Queue (Similar Cases)")

    queue = st.session_state.get("queue", [])
    if not queue:
        st.info("Run a review on the left to populate similar cases here.")
    else:
        # Bulk actions (UI stub; can be connected to a backend)
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Approve All ✅", use_container_width=True):
                st.session_state["queue"] = []
        with col2:
            if st.button("Needs Review All 🟧", use_container_width=True):
                st.session_state["queue"] = []
        with col3:
            if st.button("Reject All ❌", use_container_width=True):
                st.session_state["queue"] = []

        # Case list
        for item in queue:
            with st.expander(
                f"Similarity {item['similarity']} ｜ idx={item['idx']} ｜ reason_id={item['vote_reason_id']}"
            ):
                st.write(item.get("text", ""))
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.button("Approve ✅", key=f"ap_{item['idx']}")
                with c2:
                    st.button("Needs Review 🟧", key=f"nr_{item['idx']}")
                with c3:
                    st.button("Reject ❌", key=f"rj_{item['idx']}")

# =========================
# Footer
# =========================
st.markdown("---")
st.caption(
    "Flag Review 2.0 — Rules + Lexicons + FAISS (optional). "
    "Supports privacy-friendly degradation: rule-only mode remains explainable."
)
