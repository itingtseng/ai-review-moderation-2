# streamlit_app.py
# ------------------------------------------------------------
# AI-assisted review risk assessment
# - Policy signals + similar historical cases
# - Human moderator retains the final decision
# ------------------------------------------------------------

from typing import List

import streamlit as st

from app.decision import RuleEngine
from app.neighbor import get_index


st.set_page_config(page_title="Verdict AI", layout="wide")


POLICY_LABELS = {
    1: "Wrong Community",
    2: "Off-topic / Irrelevant",
    3: "False Information",
    4: "Affiliated with Community",
    5: "Competitor / Ex-employee",
    6: "Toxic / Hate Speech",
    7: "Privacy Violation",
    8: "Promotion / Advertising",
    9: "COVID Misinformation",
}

DEMO_USER_ID = "10745"
DEMO_POST_COUNT = 1
MAX_VISIBLE_CASES = 5
DEMO_QUEUE_USER_IDS = {
    "7574": "10745",
    "1114": "28631",
    "1116": "59302",
    "0930": "44187",
    "0117": "83054",
    "0610": "25973",
    "0704": "61842",
    "0814": "37460",
    "3310": "90521",
    "2048": "72618",
}
HISTORICAL_CASE_METADATA = [
    {"case_id": "0548", "user_id": "23817", "risk_level": "HIGH"},
    {"case_id": "1286", "user_id": "54102", "risk_level": "HIGH"},
    {"case_id": "2471", "user_id": "39584", "risk_level": "MEDIUM"},
    {"case_id": "3094", "user_id": "76031", "risk_level": "MEDIUM"},
    {"case_id": "4820", "user_id": "91426", "risk_level": "LOW"},
]
PAST_DECISION_BY_RISK = {
    "HIGH": "Flag",
    "MEDIUM": "Escalate",
    "LOW": "Pass",
}

DEMO_QUEUE = {
    "High": [
        (
            "7574",
            "Limited time! Apply now and contact John at john@example.com. The manager is an idiot—go to hell.",
            "Multiple policy signals",
        ),
        (
            "1114",
            "Contact John Smith at john@example.com or 415-555-0199 for unit 204.",
            "Privacy Violation",
        ),
        ("1116", "Go to hell you racist manager.", "Toxic / Hate Speech"),
        (
            "0930",
            "Special offer—lease today and get your application fee waived.",
            "Promotion / Advertising",
        ),
        ("0117", "The vaccine is fake and COVID is a hoax.", "COVID Misinformation"),
    ],
    "Medium": [
        (
            "0610",
            "This review is about the grocery store across the street, not the apartment.",
            "Off-topic / Irrelevant",
        ),
        (
            "0704",
            "I work for this community and highly recommend living here.",
            "Affiliated with Community",
        ),
        (
            "0814",
            "As a former employee, I know this management company cannot be trusted.",
            "Competitor / Ex-employee",
        ),
    ],
    "Low": [
        ("3310", "Great staff and clean gym. Love the dog park.", "No policy match"),
        (
            "2048",
            "The apartment was clean and maintenance responded quickly.",
            "No policy match",
        ),
    ],
}


def clear_analysis() -> None:
    for key in (
        "similar_cases",
        "analyzed_text",
        "analysis_result",
        "analysis_neighbor_signal",
        "analysis_used_fallback",
        "moderator_decision",
    ):
        st.session_state.pop(key, None)


def load_demo_review(
    post_id: str,
    review_text: str,
    user_id: str = DEMO_USER_ID,
    post_count: int = DEMO_POST_COUNT,
) -> None:
    """Open a queue item in Moderation and analyze it immediately."""
    clear_analysis()
    st.session_state["current_post_id"] = post_id
    st.session_state["current_user_id"] = user_id
    st.session_state["current_post_count"] = post_count
    st.session_state["review_text"] = review_text
    st.session_state["analysis_requested"] = True
    st.session_state["primary_tab"] = "Moderation"


def request_analysis() -> None:
    st.session_state["analysis_requested"] = True


def record_moderator_decision(decision: str) -> None:
    st.session_state["moderator_decision"] = decision


def upgrade_on_strong_evidence(per_rule: List[dict]) -> bool:
    changed = False
    for rule in per_rule:
        if rule.get("regex_hits") and rule.get("score", 0) < 1.0:
            rule["score"] = 1.0
            changed = True
    return changed


def apply_thresholds(final_score: float, high: float, med: float) -> str:
    if final_score >= high:
        return "HIGH"
    if final_score >= med:
        return "MEDIUM"
    return "LOW"


def signal_strength(score: float) -> str:
    """Describe individual policy evidence without implying an overall risk tier."""
    if score >= 0.70:
        return "Strong"
    if score >= 0.40:
        return "Moderate"
    return "Weak"


def render_risk_scale(score: float, high: float, med: float) -> None:
    score_pct = max(0.0, min(float(score), 1.0)) * 100
    med_pct = max(0.0, min(float(med), 1.0)) * 100
    high_pct = max(med_pct, min(float(high), 1.0) * 100)
    st.markdown(
        f"""
        <div style="margin: 0.5rem 0 0.25rem 0;">
            <div style="position: relative; height: 12px; border-radius: 999px;
                        background: linear-gradient(
                            90deg,
                            #2e7d32 0%, #2e7d32 {med_pct}%,
                            #f9a825 {med_pct}%, #f9a825 {high_pct}%,
                            #c62828 {high_pct}%, #c62828 100%
                        );">
                <div style="position: absolute; left: calc({score_pct}% - 7px); top: -4px;
                            width: 14px; height: 14px; border-radius: 50%;
                            background: white; border: 3px solid #111827;
                            box-shadow: 0 1px 3px rgba(0,0,0,0.35);"></div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 0.35rem;
                        font-size: 0.8rem; color: #9ca3af;">
                <span>Low</span><span>Medium</span><span>High</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def queue_button_label(
    post_id: str,
    review_text: str,
    category: str,
    user_id: str,
) -> str:
    return (
        f"**{post_id} · {category}**  \n"
        f"{review_text}  \n"
        f"`User ID: {user_id} | {DEMO_POST_COUNT} Post today`"
    )


def render_queue_items(items, key_prefix: str) -> None:
    for post_id, review_text, category in items:
        user_id = DEMO_QUEUE_USER_IDS[post_id]
        st.button(
            queue_button_label(post_id, review_text, category, user_id),
            key=f"{key_prefix}_{post_id}",
            use_container_width=True,
            on_click=load_demo_review,
            args=(post_id, review_text, user_id),
        )


def render_queue_panel(key_prefix: str) -> None:
    all_tab, passed_tab, flagged_tab, escalated_tab = st.tabs(
        ["All (10)", "Passed (2)", "Flagged (5)", "Escalated (3)"]
    )
    with all_tab:
        for risk_group, items in DEMO_QUEUE.items():
            with st.expander(
                f"{risk_group} ({len(items)})",
                expanded=risk_group == "High",
            ):
                render_queue_items(items, f"{key_prefix}_all")
    with passed_tab:
        render_queue_items(DEMO_QUEUE["Low"], f"{key_prefix}_passed")
    with flagged_tab:
        render_queue_items(DEMO_QUEUE["High"], f"{key_prefix}_flagged")
    with escalated_tab:
        render_queue_items(DEMO_QUEUE["Medium"], f"{key_prefix}_escalated")


# Default workflow opens a review immediately instead of waiting for input.
if "review_text" not in st.session_state:
    default_post_id, default_text, _ = DEMO_QUEUE["High"][0]
    load_demo_review(
        default_post_id,
        default_text,
        DEMO_QUEUE_USER_IDS[default_post_id],
    )
st.session_state.setdefault("primary_tab", "Moderation")


st.session_state.setdefault("policy_weight", 0.60)
st.session_state.setdefault("high_risk_threshold", 0.70)
st.session_state.setdefault("medium_risk_threshold", 0.40)
st.session_state.setdefault("strong_evidence", True)
st.session_state.setdefault("historical_topk", 5)

alpha = float(st.session_state["policy_weight"])
high_cut = float(st.session_state["high_risk_threshold"])
med_cut = float(st.session_state["medium_risk_threshold"])
strong_boost = bool(st.session_state["strong_evidence"])
topk = int(st.session_state["historical_topk"])


engine = RuleEngine(rules_file="app/rules.yml", alpha=alpha)
nbr = None
data_ok = True
try:
    nbr = get_index()
except Exception:
    data_ok = False


st.markdown(
    """
    <style>
    /* Queue review cards */
[class*="st-key-moderation_queue_"] button,
[class*="st-key-queue_page_"] button {
    min-height: 112px;
    padding: 16px !important;
    justify-content: flex-start !important;
}

[class*="st-key-moderation_queue_"] button p,
[class*="st-key-queue_page_"] button p {
    width: 100%;
    text-align: left !important;
    line-height: 1.55;
    font-size: 14px;
}

/* Post ID and category */
[class*="st-key-moderation_queue_"] button strong,
[class*="st-key-queue_page_"] button strong {
    font-size: 15px;
    font-weight: 600;
}

/* User metadata */
[class*="st-key-moderation_queue_"] button code,
[class*="st-key-queue_page_"] button code {
    padding: 0;
    background: transparent;
    color: #6b7280;
    font-family: inherit;
    font-size: 12px;
}

    /* Current review: read-only / disabled-like surface */
    .st-key-current_review {
        background-color: #f4f5f7;
        border-color: #e2e5e9 !important;
        border-radius: 0.5rem;
    }

    .st-key-current_review div[data-testid="stMarkdownContainer"] p {
        color: #4b5563;
    }

    /* Policy evidence cards */
    [class*="st-key-evidence_card_"] {
        min-height: 210px;
    }

    /* Active tabs */
    button[data-baseweb="tab"][aria-selected="true"],
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #2563eb !important;
        font-weight: 600 !important;
    }

    div[data-baseweb="tab-highlight"] {
        background-color: #2563eb !important;
    }

    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(1) button {
        border-color: #dc2626 !important;
        color: inherit !important;
        background: transparent !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(2) button {
        border-color: #d69e00 !important;
        color: inherit !important;
        background: transparent !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(3) button {
        border-color: #16a34a !important;
        color: inherit !important;
        background: transparent !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(4) button {
        border-color: #2563eb !important;
        color: inherit !important;
        background: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.title("⚖️ Verdict AI")
moderation_tab, queue_tab, analytics_tab, settings_tab = st.tabs(
    ["Moderation", "Queue", "Analytics", "Settings"],
    default=st.session_state.get("primary_tab", "Moderation"),
)


with moderation_tab:
    if not data_ok:
        st.warning(
            "Similar-case evidence is temporarily unavailable. "
            "Policy signals can still be analyzed."
        )
        st.button(
            "Retry similar-case service",
            key="retry_similar_service",
            on_click=request_analysis,
        )

    if st.session_state.pop("analysis_requested", False):
        review_text = st.session_state["review_text"]
        with st.spinner("Analyzing policy signals and similar cases…"):
            used_fallback = False
            if nbr is not None:
                try:
                    neighbor_conf, neighbors = nbr.search(review_text, k=topk)
                except Exception:
                    neighbor_conf, neighbors = 0.0, []
                    used_fallback = True
            else:
                neighbor_conf, neighbors = 0.0, []
                used_fallback = True

            result = engine.decide(review_text, neighbor_conf=neighbor_conf)

            if strong_boost and upgrade_on_strong_evidence(
                result.get("rules_detail", [])
            ):
                rule_score = min(
                    sum(rule.get("score", 0) for rule in result["rules_detail"]),
                    1.0,
                )
                triggered_count = sum(
                    1
                    for rule in result["rules_detail"]
                    if rule.get("score", 0) > 0
                )

                weighted_score = (
                    engine.alpha * rule_score
                    + engine.beta * neighbor_conf
                )

                multi_signal_boost = 0.10 * max(0, triggered_count - 1)

                final_score = min(
                    0.95,
                    weighted_score + multi_signal_boost,
                )
                result["rule_score"] = round(rule_score, 3)
                result["final_score"] = round(final_score, 3)

            similar_cases = []
            for position, (similarity, index) in enumerate(
                list(neighbors)[:MAX_VISIBLE_CASES]
            ):
                row = nbr.df.iloc[index] if nbr is not None else {}
                try:
                    reason_id = int(row.get("vote_reason_id", -1))
                except (TypeError, ValueError):
                    reason_id = -1
                historical_metadata = HISTORICAL_CASE_METADATA[position]
                historical_risk = historical_metadata["risk_level"]
                similar_cases.append(
                    {
                        "case_id": historical_metadata["case_id"],
                        "user_id": historical_metadata["user_id"],
                        "risk_level": historical_risk,
                        "similarity": round(float(similarity), 3),
                        "text": row.get("review_text", ""),
                        "policy_category": POLICY_LABELS.get(
                            reason_id,
                            "Other policy category",
                        ),
                        "past_decision": PAST_DECISION_BY_RISK[historical_risk],
                    }
                )

        st.session_state["analyzed_text"] = review_text
        st.session_state["analysis_result"] = result
        st.session_state["analysis_neighbor_signal"] = neighbor_conf
        st.session_state["analysis_used_fallback"] = used_fallback
        st.session_state["similar_cases"] = similar_cases
        st.session_state.pop("moderator_decision", None)

    left, right = st.columns([0.60, 0.40])

    with left:
        st.header("Review Moderation")
        with st.popover(
            "Advanced settings",
            icon=":material/tune:",
            use_container_width=False,
        ):
            st.slider(
                "Policy signal weight",
                0.0,
                1.0,
                step=0.05,
                key="policy_weight",
            )
            st.slider(
                "High-risk threshold",
                0.50,
                0.90,
                step=0.01,
                key="high_risk_threshold",
            )
            st.slider(
                "Medium-risk threshold",
                0.20,
                0.80,
                step=0.01,
                key="medium_risk_threshold",
            )
            st.checkbox(
                "Treat detected text patterns as strong evidence",
                key="strong_evidence",
            )
            st.slider(
                "Historical cases to compare",
                5,
                15,
                step=1,
                key="historical_topk",
            )
            st.caption(
                "These controls are provided for demo and evaluation purposes."
            )
        with st.container(border=True, key="current_review"):
            st.write(st.session_state["review_text"])
        post_count = st.session_state.get("current_post_count", DEMO_POST_COUNT)
        post_word = "Post" if post_count == 1 else "Posts"
        st.caption(
            f"Post ID: {st.session_state.get('current_post_id', '7574')} | "
            f"User ID: {st.session_state.get('current_user_id', DEMO_USER_ID)} | "
            f"{post_count} {post_word} today"
        )

        result = st.session_state.get("analysis_result")
        analyzed_text = st.session_state.get("analyzed_text")
        if result and analyzed_text == st.session_state["review_text"]:
            neighbor_conf = st.session_state.get("analysis_neighbor_signal", 0.0)
            risk = apply_thresholds(result["final_score"], high_cut, med_cut)
            color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}[risk]



            with st.container(key="moderator_actions"):
                action_1, action_2, action_3, action_4 = st.columns(4)
                with action_1:
                    st.button(
                        "Flag",
                        key="current_flag",
                        use_container_width=True,
                        on_click=record_moderator_decision,
                        args=("Flagged",),
                    )
                with action_2:
                    st.button(
                        "Escalate",
                        key="current_escalate",
                        use_container_width=True,
                        on_click=record_moderator_decision,
                        args=("Escalated",),
                    )
                with action_3:
                    st.button(
                        "Approve",
                        key="current_approve",
                        use_container_width=True,
                        on_click=record_moderator_decision,
                        args=("Approved",),
                    )
                with action_4:
                    st.button(
                        "Retry",
                        key="current_retry",
                        use_container_width=True,
                        on_click=request_analysis,
                    )

            if st.session_state.get("moderator_decision"):
                st.success(
                    f"Decision recorded for this demo: "
                    f"{st.session_state['moderator_decision']}."
                )

            st.subheader("Moderation Result")
            with st.expander("How scoring works"):
                matched_signal_count = sum(
                    1
                    for rule in result.get("rules_detail", [])
                    if rule.get("score", 0) > 0
                )
                base_score = (
                    result["alpha"] * result["rule_score"]
                    + result["beta"] * neighbor_conf
                )
                applied_adjustment = max(
                    0.0,
                    result["final_score"] - base_score,
                )
                st.write(
                    "The risk score combines policy evidence with similarity to "
                    "historical cases. Multiple distinct policy signals increase "
                    "review priority. It supports—but does not make—the moderator's "
                    "decision."
                )
                st.write(
                    f"**Policy evidence:** {signal_strength(result['rule_score'])} · "
                    f"{matched_signal_count} matched signals"
                )
                st.write(
                    f"**Historical similarity:** {neighbor_conf * 100:.0f}%"
                )
                st.write(
                    f"**Multiple-signal adjustment:** "
                    f"+{applied_adjustment * 100:.0f} points"
                )
                st.write(
                    f"**Overall risk score:** {result['final_score'] * 100:.0f}% · "
                    f"{risk.title()}"
                )
                st.caption(
                    f"Policy evidence weight: {result['alpha']:.0%} · "
                    f"Historical similarity weight: {result['beta']:.0%} · "
                    "+10 points per additional policy signal · "
                    f"High ≥ {high_cut:.0%} · Medium ≥ {med_cut:.0%}"
                )
            st.markdown(
                f"**Risk level:** <span style='color:{color}'><b>{risk}</b></span>",
                unsafe_allow_html=True,
            )
            st.metric("Risk score", f"{round(result['final_score'] * 100)}%")
            render_risk_scale(result["final_score"], high_cut, med_cut)
            st.caption(
                "This score indicates review risk; it is not a model confidence score."
            )

            if st.session_state.get("analysis_used_fallback"):
                st.warning(
                    "Similar-case evidence could not be refreshed. "
                    "Policy signals are still available; use Retry to try again."
                )

            st.subheader("Matched Policy Signals")
            likely = result.get("likely_reasons", [])
            if not likely:
                st.caption("No policy signals were matched.")
            for signal in likely:
                review_note = (
                    " — verify manually"
                    if signal.get("requires_human_review")
                    else ""
                )
                score = float(signal.get("score", 0))
                st.markdown(
                    f"**{signal['reason_label']}** · "
                    f"{signal_strength(score)} signal ({score:.0%}){review_note}"
                )
                st.progress(score)


            st.subheader("Why this was flagged")
            triggered_rules = [
                rule
                for rule in result.get("rules_detail", [])
                if rule.get("score", 0) > 0
            ]
            if not triggered_rules:
                st.caption("No rule-based evidence was found.")
            for row_start in range(0, len(triggered_rules), 3):
                row_rules = triggered_rules[row_start : row_start + 3]
                evidence_columns = st.columns(3)
                for column_index, rule in enumerate(row_rules):
                    card_index = row_start + column_index
                    with evidence_columns[column_index]:
                        with st.container(
                            border=True,
                            key=f"evidence_card_{card_index}",
                        ):
                            st.markdown(f"**{rule['reason_label']}**")
                            if rule.get("matched_phrases"):
                                st.markdown("**Matched phrases**")
                                st.write(
                                    " · ".join(
                                        f'“{phrase}”'
                                        for phrase in rule["matched_phrases"]
                                    )
                                )
                            if rule.get("detected_pattern"):
                                st.markdown("**Detected pattern**")
                                st.write(rule["detected_pattern"])
                            if rule.get("requires_human_review"):
                                st.caption(
                                    "This signal requires human verification."
                                )

            st.subheader("Similar Cases")
            st.caption(
                "Five closest cases are shown. Similarity is one reference signal; "
                "moderators can also inspect the content, policy category, historical "
                "risk level, and past decision."
            )
            similar_cases = st.session_state.get("similar_cases", [])
            if not similar_cases:
                st.info(
                    "Similar cases are unavailable for this analysis. "
                    "Use Retry to search again."
                )
            for case_number, item in enumerate(similar_cases, start=1):
                with st.expander(
                    f"Case {item['case_id']} · {item['similarity']:.0%} similar · "
                    f"{item['policy_category']}",
                    expanded=case_number == 1,
                ):
                    st.caption(
                        f"Case ID: {item['case_id']} | User ID: {item['user_id']}"
                    )
                    st.write(item["text"])
                    risk_level = item["risk_level"]
                    risk_color = {
                        "HIGH": "#c62828",
                        "MEDIUM": "#b77900",
                        "LOW": "#2e7d32",
                    }[risk_level]
                    st.markdown(
                        f"**Risk level:** "
                        f"<span style='color:{risk_color}'><b>{risk_level.title()}</b></span>",
                        unsafe_allow_html=True,
                    )
                    decision = item["past_decision"]
                    if decision == "Flag":
                        st.error("Past decision: Flag")
                    elif decision == "Escalate":
                        st.warning("Past decision: Escalate")
                    else:
                        st.success("Past decision: Pass")

    with right:
        st.header("Moderation Queue")
        st.caption(
            "Select any review to open it in Moderation and refresh its analysis."
        )
        render_queue_panel("moderation_queue")


with queue_tab:
    st.header("Moderation Queue")
    st.caption(
        "Select any review to open it in Moderation and refresh its analysis."
    )
    render_queue_panel("queue_page")


with analytics_tab:
    st.header("Analytics")
    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Reviewed today", "128", "+12%")
    metric_2.metric("Escalation rate", "8%", "-2%")
    metric_3.metric("Median review time", "42 sec", "-6 sec")
    st.caption("Synthetic metrics for navigation and workflow context.")


with settings_tab:
    st.header("Settings")
    st.toggle("Require human approval for high-risk cases", value=True)
    st.toggle("Show similar-case evidence", value=True)
    st.selectbox("Default queue", ["All reviews", "High priority", "Assigned to me"])
    st.caption("Demo-only settings; no production configuration is changed.")


st.markdown("---")
st.caption("AI-assisted review support. Final decisions remain with moderators.")
