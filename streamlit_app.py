# streamlit_app.py
# ------------------------------------------------------------
# Flag Review 2.0 — Meta Trust & Safety + Moderator Queue
# - 規則分 (rules) + 語意相似度 (neighbors) 混合
# - 找不到資料時自動 fallback：僅用規則分 (neighbor_conf = 0)
# - 參數可在 Sidebar 調整
# ------------------------------------------------------------

import streamlit as st
from typing import List, Tuple

# 你的專案內模組
from app.decision import RuleEngine
from app.neighbor import get_index  # 可能在雲端找不到資料，下面有 try/except

st.set_page_config(
    page_title="Flag Review 2.0 — Meta T&S + Queue",
    layout="wide",
)

# =========================
# Sidebar：可調參數
# =========================
st.sidebar.header("🛠️ 審查參數")
alpha = st.sidebar.slider("Rule Weight α（規則權重）", 0.0, 1.0, 0.60, 0.05)
high_cut = st.sidebar.slider("HIGH 門檻", 0.50, 0.90, 0.70, 0.01)
med_cut = st.sidebar.slider("MEDIUM 門檻", 0.20, 0.80, 0.40, 0.01)
strong_boost = st.sidebar.checkbox("命中『強證據』時將該規則分設為 1.0（建議開）", value=True)
topk = st.sidebar.slider("相似案例 K", 3, 15, 5, 1)

st.sidebar.caption(
    "Tips：\n"
    "- Promotion/Privacy/Toxic/COVID → 高訊號，建議提升規則分\n"
    "- Off-topic → 多倚賴語意相似度與 HITL"
)

# =========================
# 初始化：規則引擎
# =========================
engine = RuleEngine(rules_file="app/rules.yml", alpha=alpha)

# =========================
# 嘗試載入語意檢索索引（FAISS）
# 找不到資料時 → 退化為 rule-only 模式
# =========================
nbr = None
data_ok = True
err_msg = ""
try:
    nbr = get_index()
except Exception as e:
    data_ok = False
    err_msg = str(e)

# 介面提示（僅在資料/索引不可用時顯示）
if not data_ok:
    st.warning(
        "⚠️ 語意檢索資料源尚未就緒：\n\n"
        "- 已改為僅使用規則分數（neighbor_conf=0）。\n"
        "- 解法：\n"
        "  1) 將原始資料上傳到 repo（`data/raw/...`），或\n"
        "  2) 新增示例檔 `data/samples/sample_reviews.csv`（建議），或\n"
        "  3) 在 Secrets/環境變數設定 `DATA_PATH` 指向你的檔案。\n\n"
        f"詳情：{err_msg}"
    )

# =========================
# 版面配置
# =========================
left, right = st.columns([0.60, 0.40])

# =========================
# 小工具：風險等級
# =========================
def apply_thresholds(final_score: float, high: float, med: float) -> str:
    if final_score >= high:
        return "HIGH"
    if final_score >= med:
        return "MEDIUM"
    return "LOW"

# =========================
# 小工具：強證據提升（將命中 regex 的規則 score 拉到 1.0）
# =========================
def upgrade_on_strong_evidence(per_rule: List[dict]) -> bool:
    """
    per_rule: [
      {"reason_label": "...", "weight": 0.7, "score": 0.3, "regex_hits": [...], "keyword_hits": [...], "explanation": "..."},
      ...
    ]
    命中 regex_hits 的規則通常代表高可靠度證據（URL/電話/Email/PII/辱罵語等）
    """
    changed = False
    for r in per_rule:
        if r.get("regex_hits"):
            if r.get("score", 0) < 1.0:
                r["score"] = 1.0
                changed = True
    return changed

# =========================
# 左側：輸入 + 結果（Meta T&S 卡）
# =========================
with left:
    st.title("Flag Review 2.0")
    st.caption("Meta Trust & Safety 風格 + Moderator Queue（混合版）")

    user_text = st.text_area(
        "貼上待審查的評論：",
        height=160,
        placeholder="e.g., Limited time! Apply now and schedule a tour. Visit our website or call now."
    )

    run_btn = st.button("AI 判斷", type="primary", use_container_width=True)

    if run_btn:
        if not user_text.strip():
            st.warning("請先輸入文字")
        else:
            # 1) 語意相似度（若索引可用）
            if nbr is not None:
                neighbor_conf, neighbors = nbr.search(user_text, k=topk)
            else:
                neighbor_conf, neighbors = 0.0, []

            # 2) 規則打分（rule_score + rules_detail + likely_reasons + alpha/beta）
            result = engine.decide(user_text, neighbor_conf=neighbor_conf)

            # 3) 命中強證據時，將該規則分提升至 1.0，並重算 final
            if strong_boost:
                if upgrade_on_strong_evidence(result.get("rules_detail", [])):
                    rule_score = sum(r.get("score", 0) for r in result["rules_detail"])
                    rule_score = min(rule_score, 1.0)
                    final_score = engine.alpha * rule_score + engine.beta * neighbor_conf
                    result["rule_score"] = round(rule_score, 3)
                    result["final_score"] = round(final_score, 3)

            # 4) 依門檻決定風險等級
            risk = apply_thresholds(result["final_score"], high_cut, med_cut)
            color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}[risk]

            # === Meta T&S 卡（結論） ===
            st.markdown(
                f"### ✅ 審查結論：<span style='color:{color}'><b>{risk}</b></span>",
                unsafe_allow_html=True,
            )
            st.write(
                f"**final** = {result['final_score']}  |  "
                f"**rule** = {result['rule_score']}  |  "
                f"**neighbor** = {round(neighbor_conf, 3)}"
            )
            st.caption(
                f"α（規則）={result['alpha']} / β（相似案例）={result['beta']} ｜ "
                f"HIGH≥{high_cut} / MED≥{med_cut}"
            )

            # === 可能原因（Top 3） ===
            st.subheader("可能原因（Top 3）")
            likely = result.get("likely_reasons", [])
            if not likely:
                st.write("- 無規則命中")
            else:
                for r in likely:
                    st.write(f"- **{r['reason_label']}** 〔score={r['score']}〕")

            # === 解釋卡（Evidence） ===
            st.subheader("解釋卡（Evidence）")
            for r in result.get("rules_detail", []):
                if r.get("score", 0) <= 0:
                    continue
                with st.expander(f"{r['reason_label']}（w={r['weight']} → {r['score']}）"):
                    if r.get("keyword_hits"):
                        st.write("**關鍵片語命中**：", ", ".join(r["keyword_hits"]))
                    if r.get("regex_hits"):
                        st.write("**正則命中**：URL / 電話 / Email / 促銷 / 個資 / 疫情等")
                    if r.get("explanation"):
                        st.caption(r["explanation"])

            # === 把近鄰塞進右側 Queue（若可用） ===
            st.session_state["queue"] = []
            for sim, idx in neighbors:
                # 由 neighbor.get_index().df 取得原文等欄位
                row = nbr.df.iloc[idx] if nbr is not None else {}
                st.session_state["queue"].append({
                    "idx": int(idx),
                    "similarity": round(float(sim), 3),
                    "text": row.get("review_text", ""),
                    "vote_reason_id": int(row.get("vote_reason_id", -1)) if "vote_reason_id" in row else -1,
                })

            if neighbors:
                st.success("已更新右側 Moderator Queue（相似案例 Top-K）")
            elif nbr is None:
                st.info("目前為 rule-only 模式：未提供相似案例（請上傳資料或設定 DATA_PATH）。")

# =========================
# 右側：Moderator Queue（Product Pitch 區塊）
# =========================
with right:
    st.header("Moderator Queue（相似案例）")

    queue = st.session_state.get("queue", [])
    if not queue:
        st.info("按下左側「AI 判斷」後，這裡會列出 Top-K 相似案例。")
    else:
        # 批次操作（這裡僅示意 UI；實務可接後端記錄）
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("全部 Approve ✅", use_container_width=True):
                st.session_state["queue"] = []
        with col2:
            if st.button("全部 Needs Review 🟧", use_container_width=True):
                st.session_state["queue"] = []
        with col3:
            if st.button("全部 Reject ❌", use_container_width=True):
                st.session_state["queue"] = []

        # 清單
        for item in queue:
            with st.expander(
                f"相似度 {item['similarity']} ｜ idx={item['idx']} ｜ reason_id={item['vote_reason_id']}"
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
    "本系統支援隱私友善降級：在無語料時以規則引擎運作並保留可解釋性。"
)
