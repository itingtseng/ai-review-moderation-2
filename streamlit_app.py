# streamlit_app.py
import streamlit as st
from app.decision import RuleEngine
from app.neighbor import get_index

st.set_page_config(page_title="Flag Review 2.0 — Meta T&S + Queue", layout="wide")

# ---- Sidebar: 參數 ----
st.sidebar.header("審查參數")
alpha = st.sidebar.slider("Rule Weight α（規則權重）", 0.0, 1.0, 0.60, 0.05)
high_cut = st.sidebar.slider("HIGH 門檻", 0.5, 0.9, 0.70, 0.01)
med_cut = st.sidebar.slider("MEDIUM 門檻", 0.2, 0.8, 0.40, 0.01)
strong_boost = st.sidebar.checkbox("命中強證據時：提升規則分至 1.0（建議開）", value=True)
topk = st.sidebar.slider("相似案例 K", 3, 15, 5, 1)

# ---- 左右欄佈局 ----
left, right = st.columns([0.6, 0.4])

# ---- 初始化 引擎 / 索引 ----
engine = RuleEngine(rules_file="app/rules.yml", alpha=alpha)
nbr = get_index()

# ---- Session state for queue actions ----
if "queue" not in st.session_state:
    st.session_state.queue = []  # [(text, sim, idx), ...]

def apply_thresholds(result, high=0.70, med=0.40):
    fs = result["final_score"]
    if fs >= high: return "HIGH"
    if fs >= med: return "MEDIUM"
    return "LOW"

def upgrade_on_strong_evidence(per_rule):
    # 若勾選強證據升級：只要任何規則有 regex_hits 就把它那條 score 拉滿到 1.0
    changed = False
    for r in per_rule:
        if r["regex_hits"]:
            if r["score"] < 1.0:
                r["score"] = 1.0
                changed = True
    return changed

# ---- 左側：Meta T&S 卡 + Explainability ----
with left:
    st.title("Flag Review 2.0")
    st.caption("Meta Trust & Safety 風格 + Moderator Queue（混合版）")

    user_text = st.text_area("貼上待審查的評論：", height=160, placeholder="e.g., Limited time! Apply now and schedule a tour. Visit our website or call now.")

    if st.button("AI 判斷", type="primary", use_container_width=True):
        if not user_text.strip():
            st.warning("請先輸入文字")
        else:
            # 1) 語意檢索信心 + 近鄰
            neighbor_conf, neighbors = nbr.search(user_text, k=topk)

            # 2) 規則打分
            result = engine.decide(user_text, neighbor_conf=neighbor_conf)

            # 2.1 強證據升級（選用）
            if strong_boost:
                if upgrade_on_strong_evidence(result["rules_detail"]):
                    # 重新彙總分數
                    rule_score = sum(r["score"] for r in result["rules_detail"])
                    rule_score = min(rule_score, 1.0)
                    final_score = engine.alpha * rule_score + engine.beta * neighbor_conf
                    result["rule_score"] = round(rule_score, 3)
                    result["final_score"] = round(final_score, 3)

            # 2.2 依客製門檻決定等級
            risk = apply_thresholds(result, high_cut, med_cut)
            result["risk_level"] = risk

            # --- Meta T&S 卡 ---
            color = {"HIGH":"red","MEDIUM":"orange","LOW":"green"}[risk]
            st.markdown(f"### ✅ 審查結論：<span style='color:{color}'><b>{risk}</b></span>", unsafe_allow_html=True)
            st.write(f"final={result['final_score']}  | rule={result['rule_score']}  | neighbor={round(neighbor_conf,3)}")
            st.caption(f"α（規則）={result['alpha']} / β（相似案例）={result['beta']}  ｜ HIGH≥{high_cut} / MED≥{med_cut}")

            st.subheader("可能原因（Top 3）")
            if not result["likely_reasons"]:
                st.write("- 無規則命中")
            for r in result["likely_reasons"]:
                st.write(f"- **{r['reason_label']}** 〔score={r['score']}〕")

            st.subheader("解釋卡（Evidence）")
            for r in result["rules_detail"]:
                if r["score"] <= 0:
                    continue
                with st.expander(f"{r['reason_label']}（w={r['weight']} → {r['score']}）"):
                    if r["keyword_hits"]:
                        st.write("**關鍵片語命中**：", ", ".join(r["keyword_hits"]))
                    if r["regex_hits"]:
                        st.write("**正則命中**：URL/電話/Email/促銷/個資/疫情等")
                    st.caption(r["explanation"])

            # 把近鄰塞進 queue（右側）
            st.session_state.queue = []
            for sim, idx in neighbors:
                row = nbr.df.iloc[idx]
                st.session_state.queue.append({
                    "idx": int(idx),
                    "similarity": round(float(sim), 3),
                    "text": row.get("review_text", ""),
                    "vote_reason_id": int(row.get("vote_reason_id", -1))
                })
            st.success("已更新右側 Moderator Queue（相似案例 Top-K）")

# ---- 右側：Moderator Queue（Product Pitch 區塊）----
with right:
    st.header("Moderator Queue（相似案例）")

    if not st.session_state.queue:
        st.info("按下左側「AI 判斷」後，這裡會列出 Top-K 相似案例。")
    else:
        # 批次操作欄位
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button("全部 Approve", use_container_width=True):
                st.session_state.queue.clear()
        with action_col2:
            if st.button("全部 Needs Review", use_container_width=True):
                st.session_state.queue.clear()
        with action_col3:
            if st.button("全部 Reject", use_container_width=True):
                st.session_state.queue.clear()

        # 列表
        for item in st.session_state.queue:
            with st.expander(f"相似度 {item['similarity']} ｜ idx={item['idx']} ｜ reason_id={item['vote_reason_id']}"):
                st.write(item["text"])
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("Approve ✅", key=f"ap_{item['idx']}"):
                        pass
                with c2:
                    if st.button("Needs Review 🟧", key=f"nr_{item['idx']}"):
                        pass
                with c3:
                    if st.button("Reject ❌", key=f"rj_{item['idx']}"):
                        pass
