# frontend/streamlit_app.py
import streamlit as st
import requests

API = st.secrets.get("API_URL", "http://127.0.0.1:8010")

st.set_page_config(page_title="AI Review Moderation 2.0", layout="wide")
st.title("🛡️ AI Review Moderation 2.0")

with st.sidebar:
    st.caption("Backend API")
    api = st.text_input("API URL", value=API)

text = st.text_area("貼上評論內容", height=160, placeholder="Enter review text…")
top_k = st.slider("相似案例 (Top-K)", 1, 10, 5)

if st.button("分析"):
    if not text.strip():
        st.warning("請輸入評論內容")
    else:
        with st.spinner("分析中…"):
            r = requests.post(f"{api}/classify", json={"text": text, "top_k": top_k}, timeout=90)
            if r.status_code != 200:
                st.error(f"API error: {r.status_code} {r.text}")
            else:
                out = r.json()
                col1, col2 = st.columns([1,1])
                with col1:
                    st.subheader("判定")
                    st.write("**Flag**:", out.get("flag"))
                    st.write("**Reason**:", out.get("reason"))
                    st.write("**Policy Ref**:", out.get("policy_ref"))
                with col2:
                    st.subheader("相似案例")
                    for c in out.get("similar_cases", []):
                        st.markdown(f"- **#{c['id']}** (label: {c['label']}, score: {c['score']:.3f}) — {c['text'][:180]}…")
