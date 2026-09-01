# streamlit_app.py
# ------------------------------------------------------------
# AI-assisted review risk assessment
# - Policy signals + similar historical cases
# - Human moderator retains the final decision
# ------------------------------------------------------------

import html
import re
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
DEMO_QUEUE_RISK_SCORES = {
    "7574": 0.89,
    "1114": 0.84,
    "1116": 0.82,
    "0930": 0.76,
    "0117": 0.73,
    "0610": 0.64,
    "0704": 0.57,
    "0814": 0.48,
    "3310": 0.31,
    "2048": 0.24,
}
HISTORICAL_CASE_METADATA = [
    {
        "case_id": "0548",
        "user_id": "23817",
        "risk_level": "HIGH",
        "risk_score": 0.87,
    },
    {
        "case_id": "1286",
        "user_id": "54102",
        "risk_level": "HIGH",
        "risk_score": 0.79,
    },
    {
        "case_id": "2471",
        "user_id": "39584",
        "risk_level": "MEDIUM",
        "risk_score": 0.62,
    },
    {
        "case_id": "3094",
        "user_id": "76031",
        "risk_level": "MEDIUM",
        "risk_score": 0.55,
    },
    {
        "case_id": "4820",
        "user_id": "91426",
        "risk_level": "LOW",
        "risk_score": 0.28,
    },
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
            "Limited time! Apply now and contact John at john@example.com. The manager was rude and called a resident an idiot.",
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


def highlight_review_matches(review_text: str, rules_detail: List[dict]) -> str:
    """Return escaped review HTML with detected phrases highlighted."""
    phrases = {
        str(phrase).strip()
        for rule in rules_detail
        for phrase in rule.get("matched_phrases", [])
        if str(phrase).strip()
    }
    if not phrases:
        return html.escape(review_text)

    phrase_pattern = re.compile(
        "|".join(re.escape(phrase) for phrase in sorted(phrases, key=len, reverse=True)),
        re.IGNORECASE,
    )
    highlighted_parts = []
    last_end = 0
    for match in phrase_pattern.finditer(review_text):
        highlighted_parts.append(html.escape(review_text[last_end : match.start()]))
        highlighted_parts.append(
            "<span class='current-review-match'>"
            f"{html.escape(match.group(0))}</span>"
        )
        last_end = match.end()
    highlighted_parts.append(html.escape(review_text[last_end:]))
    return "".join(highlighted_parts)


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
    risk_group: str,
    risk_score: float,
) -> str:
    return (
        f"**{risk_group}** **{risk_score:.0%}** **{category}**  \n"
        f"{review_text}  \n"
        f"`Post ID: {post_id} | User ID: {user_id} | "
        f"{DEMO_POST_COUNT} Post today`"
    )


def render_queue_items(items, key_prefix: str, risk_group: str) -> None:
    for post_id, review_text, category in items:
        user_id = DEMO_QUEUE_USER_IDS[post_id]
        risk_score = DEMO_QUEUE_RISK_SCORES[post_id]
        selection_state = (
            "selected"
            if st.session_state.get("current_post_id") == post_id
            else "unselected"
        )
        with st.container(
            key=(
                f"{key_prefix}_queue_{selection_state}_"
                f"risk_{risk_group.lower()}_{post_id}"
            )
        ):
            st.button(
                queue_button_label(
                    post_id,
                    review_text,
                    category,
                    user_id,
                    risk_group,
                    risk_score,
                ),
                key=f"{key_prefix}_{post_id}",
                use_container_width=True,
                on_click=load_demo_review,
                args=(post_id, review_text, user_id),
            )


def render_queue_panel(key_prefix: str) -> None:
    all_tab, passed_tab, flagged_tab, escalated_tab = st.tabs(
        ["Pending (10)", "Passed (2)", "Flagged (5)", "Escalated (3)"]
    )
    with all_tab:
        for risk_group, items in DEMO_QUEUE.items():
            with st.expander(
                f"{risk_group} ({len(items)})",
                expanded=risk_group == "High",
            ):
                render_queue_items(items, f"{key_prefix}_all", risk_group)
    with passed_tab:
        render_queue_items(DEMO_QUEUE["Low"], f"{key_prefix}_passed", "Low")
    with flagged_tab:
        render_queue_items(DEMO_QUEUE["High"], f"{key_prefix}_flagged", "High")
    with escalated_tab:
        render_queue_items(
            DEMO_QUEUE["Medium"],
            f"{key_prefix}_escalated",
            "Medium",
        )


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

/* Currently opened queue item */
[class*="_queue_selected_"] button {
    border-color: #2563eb !important;
    background: #eff6ff !important;
    box-shadow: inset 3px 0 0 #2563eb;
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

/* Risk label at the start of each queue card */
[class*="_risk_high_"] button strong:first-child,
[class*="_risk_medium_"] button strong:first-child,
[class*="_risk_low_"] button strong:first-child {
    display: inline-block;
    margin-right: 0.2rem;
    padding: 0.18rem 0.5rem;
    border-radius: 999px;
    color: white;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.3;
}

[class*="_risk_high_"] button strong:first-child {
    color: #c62828;
    background: rgba(198, 40, 40, 0.2);
}

[class*="_risk_medium_"] button strong:first-child {
    color: #b77900;
    background: rgba(183, 121, 0, 0.2);
}

[class*="_risk_low_"] button strong:first-child {
    color: #2e7d32;
    background: rgba(46, 125, 50, 0.2);
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

    .current-review-match,
    .current-review-match a {
        color: #dc2626 !important;
    }

    /* Similar historical case cards */
    .similar-case-card {
        margin-bottom: 0.75rem;
        overflow: hidden;
        border: 1px solid #d9dde3;
        border-radius: 0.55rem;
        background: white;
    }

    .similar-case-card summary {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.9rem 1rem;
        cursor: pointer;
        list-style: none;
        user-select: none;
    }

    .similar-case-card summary::-webkit-details-marker {
        display: none;
    }

    .similar-case-heading {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        min-width: 0;
        color: #31333f;
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.35;
    }

    .similar-case-chevron {
        color: #64748b;
        font-size: 0.9rem;
        transition: transform 0.15s ease;
    }

    .similar-case-card[open] .similar-case-chevron {
        transform: rotate(180deg);
    }

    .similar-case-decision {
        flex-shrink: 0;
        padding: 0.22rem 0.6rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        line-height: 1.3;
    }

    .similar-case-decision.flag {
        color: #dc2626;
        background: #fee2e2;
    }

    .similar-case-decision.escalate {
        color: #b77900;
        background: #fef3c7;
    }

    .similar-case-decision.pass {
        color: #15803d;
        background: #dcfce7;
    }

    .similar-case-body {
        padding: 0 1rem 1rem;
        border-top: 1px solid #eef0f3;
    }

    .similar-case-review {
        margin: 0.85rem 0 0.4rem;
        padding: 0.75rem 0.85rem;
        border: 1px solid #e2e5e9;
        border-radius: 0.5rem;
        background: #f4f5f7;
        color: #4b5563;
        line-height: 1.5;
    }

    .similar-case-meta {
        color: #6b7280;
        font-size: 0.78rem;
    }

    .similar-case-risk-row {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        align-items: center;
        gap: 1rem;
        margin: 0.85rem 0 0.55rem;
    }

    .similar-case-risk-summary {
        display: flex;
        align-items: center;
        gap: 0.65rem;
    }

    .similar-case-risk-label {
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        color: white;
        font-size: 0.9rem;
        font-weight: 700;
        line-height: 1.3;
    }

    .similar-case-risk-score {
        color: #31333f;
        font-size: 1.25rem;
        font-weight: 700;
    }

    .similar-case-risk-scale {
        min-width: 0;
    }

    .similar-case-risk-track {
        position: relative;
        height: 10px;
        border-radius: 999px;
    }

    .similar-case-risk-marker {
        position: absolute;
        top: -4px;
        width: 12px;
        height: 12px;
        border: 3px solid #111827;
        border-radius: 50%;
        background: white;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }

    .similar-case-risk-labels {
        display: flex;
        justify-content: space-between;
        margin-top: 0.3rem;
        color: #9ca3af;
        font-size: 0.72rem;
    }

    @media (max-width: 720px) {
        .similar-case-risk-row {
            grid-template-columns: 1fr;
        }
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

    /* Product header */
    .verdict-header {
        min-height: 88px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: relative;
    }

    .verdict-brand {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        min-width: 0;
    }

    .verdict-brand h1 {
        margin: 0;
        padding: 0;
        font-size: 2.75rem;
        line-height: 1.15;
        color: #31333f;
    }

    .verdict-badge {
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
        padding: 0.2rem 0.5rem;
        border: 1px solid #94a3b8;
        border-radius: 0.3rem;
        color: #334155;
        background: #f8fafc;
        font-size: 0.75rem;
        font-weight: 500;
        line-height: 1.2;
    }

    .verdict-profile {
        position: relative;
        z-index: 30;
    }

    .verdict-profile summary {
        list-style: none;
        display: flex;
        align-items: center;
        gap: 0.3rem;
        cursor: pointer;
        user-select: none;
    }

    .verdict-profile summary::-webkit-details-marker {
        display: none;
    }

    .verdict-avatar {
        width: 2.25rem;
        height: 2.25rem;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #bfdbfe;
        color: #1e3a8a;
        font-size: 0.85rem;
        font-weight: 600;
    }

    .verdict-profile-caret {
        color: #2563eb;
        font-size: 0.75rem;
    }

    .verdict-profile-panel {
        position: absolute;
        top: calc(100% + 0.5rem);
        right: 0;
        width: 12rem;
        padding: 0.8rem;
        border: 1px solid #e2e8f0;
        border-radius: 0.5rem;
        background: white;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.14);
    }

    .verdict-profile-panel strong,
    .verdict-profile-panel span {
        display: block;
    }

    .verdict-profile-panel span {
        margin-top: 0.15rem;
        color: #64748b;
        font-size: 0.8rem;
    }

    /* Desktop header: keep the primary navigation beside the product title. */
    @media (min-width: 900px) {
        div[data-testid="stMainBlockContainer"]
          > div[data-testid="stVerticalBlock"]
          > div[data-testid="stTabs"]
          > div
          > div
          > div[data-baseweb="tab-list"] {
            justify-content: flex-end;
            padding-right: 4.5rem;
            position: relative;
            z-index: 10;
            transform: translateY(-68px);
        }
    }

    @media (max-width: 899px) {
        .verdict-brand {
            max-width: calc(100% - 3.5rem);
            flex-wrap: wrap;
            row-gap: 0.35rem;
        }

        .verdict-brand h1 {
            font-size: 2.25rem;
        }
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

    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(1) button:hover {
        color: #dc2626 !important;
        background: rgba(220, 38, 38, 0.2) !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(1) button:hover p {
        color: #dc2626 !important;
    }

    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(2) button:hover {
        color: #d69e00 !important;
        background: rgba(214, 158, 0, 0.2) !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(2) button:hover p {
        color: #d69e00 !important;
    }

    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(3) button:hover {
        color: #16a34a !important;
        background: rgba(22, 163, 74, 0.2) !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(3) button:hover p {
        color: #16a34a !important;
    }

    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(4) button:hover {
        color: #2563eb !important;
        background: rgba(37, 99, 235, 0.2) !important;
    }
    .st-key-moderator_actions div[data-testid="stHorizontalBlock"]
      > div[data-testid="stColumn"]:nth-child(4) button:hover p {
        color: #2563eb !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <div class="verdict-header">
        <div class="verdict-brand">
            <h1>⚖️ Verdict AI</h1>
            <span class="verdict-badge">Trust &amp; Safety</span>
        </div>
        <details class="verdict-profile">
            <summary aria-label="Open profile menu">
                <span class="verdict-avatar">YC</span>
                <span class="verdict-profile-caret">▾</span>
            </summary>
            <div class="verdict-profile-panel">
                <strong>YC</strong>
                <span>Moderator · Signed in</span>
            </div>
        </details>
    </div>
    """,
    unsafe_allow_html=True,
)
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
                        "risk_score": historical_metadata["risk_score"],
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

    queue_column, review_column = st.columns([0.40, 0.60])

    with review_column:
        review_heading, settings_control = st.columns(
            [0.68, 0.32],
            vertical_alignment="center",
        )
        with review_heading:
            st.header("Review Moderation")
        with settings_control:
            with st.popover(
                "Advanced settings",
                icon=":material/tune:",
                use_container_width=True,
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
        review_result = st.session_state.get("analysis_result") or {}
        review_rules = (
            review_result.get("rules_detail", [])
            if st.session_state.get("analyzed_text")
            == st.session_state["review_text"]
            else []
        )
        with st.container(border=True, key="current_review"):
            st.markdown(
                highlight_review_matches(
                    st.session_state["review_text"],
                    review_rules,
                ),
                unsafe_allow_html=True,
            )
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
            color = {
                "HIGH": "#c62828",
                "MEDIUM": "#b77900",
                "LOW": "#2e7d32",
            }[risk]



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

            result_heading, scoring_control = st.columns(
                [0.58, 0.42],
                vertical_alignment="center",
            )
            with result_heading:
                st.subheader("Moderation Result")
            with scoring_control:
                with st.popover(
                    "How scoring works",
                    use_container_width=True,
                ):
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
                    similar_case_count = len(
                        st.session_state.get("similar_cases", [])
                    )
                    st.write(
                        f"This review matched {matched_signal_count} policy signals. "
                        "Similar historical cases provide supporting context, and "
                        "multiple policy matches increase review priority. The score "
                        "supports—but does not make—the moderator's decision."
                    )
                    st.write(
                        f"**Policy signals matched:** {matched_signal_count}"
                    )
                    st.write(
                        f"**Historical context:** {similar_case_count} similar cases found"
                    )
                    st.write(
                        f"**Overall risk score:** "
                        f"{result['final_score'] * 100:.0f}% · {risk.title()}"
                    )
                    with st.expander("Technical details"):
                        policy_contribution = (
                            result["alpha"] * result["rule_score"]
                        )
                        similarity_contribution = result["beta"] * neighbor_conf
                        st.write(
                            f"Policy evidence: {result['rule_score']:.0%} signal × "
                            f"{result['alpha']:.0%} weight = "
                            f"{policy_contribution * 100:.0f} points"
                        )
                        st.write(
                            f"Historical cases: {neighbor_conf:.0%} aggregated "
                            f"similarity signal × {result['beta']:.0%} weight = "
                            f"{similarity_contribution * 100:.0f} points"
                        )
                        st.write(
                            f"Multiple policy matches: "
                            f"+{applied_adjustment * 100:.0f} points"
                        )
                        st.caption(
                            "+10 points per additional policy signal · "
                            f"High ≥ {high_cut:.0%} · Medium ≥ {med_cut:.0%}"
                        )
            risk_summary, risk_scale = st.columns(
                [0.24, 0.76],
                gap="small",
                vertical_alignment="center",
            )
            with risk_summary:
                st.markdown(
                    "<div style='display:flex; align-items:center; gap:0.65rem;'>"
                    f"<span style='background:{color}; color:white; "
                    "font-size:1rem; font-weight:700; padding:0.25rem 0.65rem; "
                    f"border-radius:999px;'>{risk.title()}</span>"
                    f"<span style='font-size:1.5rem; font-weight:700;'>"
                    f"{round(result['final_score'] * 100)}%</span></div>",
                    unsafe_allow_html=True,
                )
            with risk_scale:
                render_risk_scale(result["final_score"], high_cut, med_cut)
                st.caption(
                    "This score indicates review risk; it is not a model "
                    "confidence score."
                )

            if st.session_state.get("analysis_used_fallback"):
                st.warning(
                    "Similar-case evidence could not be refreshed. "
                    "Policy signals are still available; use Retry to try again."
                )

            st.subheader("Matched Policy Signals")
            likely = result.get("likely_reasons", [])
            signal_scores = {
                signal.get("reason_id", signal.get("reason_label")): float(
                    signal.get("score", 0)
                )
                for signal in likely
            }
            triggered_rules = [
                rule
                for rule in result.get("rules_detail", [])
                if rule.get("score", 0) > 0
            ]
            if not triggered_rules:
                st.caption("No policy signals were matched.")
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
                            signal_key = rule.get(
                                "reason_id", rule.get("reason_label")
                            )
                            score = signal_scores.get(
                                signal_key,
                                float(rule.get("score", 0)),
                            )
                            st.markdown(
                                "<div style='display:flex; align-items:flex-start; "
                                "justify-content:space-between; gap:0.5rem; "
                                "font-size:1rem; font-weight:700; line-height:1.4;'>"
                                f"<span>{rule['reason_label']}</span>"
                                f"<span style='flex-shrink:0; text-align:right;'>"
                                f"{score:.0%}</span></div>",
                                unsafe_allow_html=True,
                            )
                            st.progress(score)
                            if rule.get("matched_phrases"):
                                st.markdown("**Matched phrases**")
                                st.write(
                                    " · ".join(
                                        f"“{phrase}”"
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
            fallback_risk_scores = {"HIGH": 0.82, "MEDIUM": 0.58, "LOW": 0.28}
            case_medium_pct = max(0.0, min(float(med_cut), 1.0)) * 100
            case_high_pct = max(
                case_medium_pct,
                min(float(high_cut), 1.0) * 100,
            )
            for case_number, item in enumerate(similar_cases, start=1):
                risk_level = item["risk_level"]
                risk_color = {
                    "HIGH": "#c62828",
                    "MEDIUM": "#b77900",
                    "LOW": "#2e7d32",
                }[risk_level]
                risk_score = item.get(
                    "risk_score",
                    fallback_risk_scores[risk_level],
                )
                risk_score_pct = max(0.0, min(float(risk_score), 1.0)) * 100
                decision = item["past_decision"]
                decision_class = decision.lower()
                expanded = " open" if case_number == 1 else ""
                policy_category = html.escape(str(item["policy_category"]))
                case_text = str(item["text"])
                case_rule_result = engine.decide(
                    case_text,
                    neighbor_conf=0.0,
                )
                review_content = highlight_review_matches(
                    case_text,
                    case_rule_result.get("rules_detail", []),
                )
                case_id = html.escape(str(item["case_id"]))
                user_id = html.escape(str(item["user_id"]))
                st.markdown(
                    f"""
                    <details class="similar-case-card"{expanded}>
                        <summary>
                            <span class="similar-case-heading">
                                <span class="similar-case-chevron">⌄</span>
                                <span>{item['similarity']:.0%} {policy_category}</span>
                            </span>
                            <span class="similar-case-decision {decision_class}">
                                {decision}
                            </span>
                        </summary>
                        <div class="similar-case-body">
                            <div class="similar-case-risk-row">
                                <div class="similar-case-risk-summary">
                                    <span class="similar-case-risk-label"
                                          style="background:{risk_color};">
                                        {risk_level.title()}
                                    </span>
                                    <span class="similar-case-risk-score">
                                        {risk_score:.0%}
                                    </span>
                                </div>
                                <div class="similar-case-risk-scale">
                                    <div class="similar-case-risk-track"
                                         style="background:linear-gradient(
                                            90deg,
                                            #2e7d32 0%,
                                            #2e7d32 {case_medium_pct}%,
                                            #f9a825 {case_medium_pct}%,
                                            #f9a825 {case_high_pct}%,
                                            #c62828 {case_high_pct}%,
                                            #c62828 100%);">
                                        <span class="similar-case-risk-marker"
                                              style="left:calc(
                                                {risk_score_pct}% - 6px);">
                                        </span>
                                    </div>
                                    <div class="similar-case-risk-labels">
                                        <span>Low</span>
                                        <span>Medium</span>
                                        <span>High</span>
                                    </div>
                                </div>
                            </div>
                            <div class="similar-case-review">{review_content}</div>
                            <div class="similar-case-meta">
                                Case ID: {case_id} | User ID: {user_id}
                            </div>
                        </div>
                    </details>
                    """,
                    unsafe_allow_html=True,
                )

    with queue_column:
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
