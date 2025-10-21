# backend/classifier.py
import os, json
from pathlib import Path
from dotenv import load_dotenv
from .retriever import retrieve_similar
from openai import OpenAI

load_dotenv()
MODEL = os.getenv("MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM = (
 "你是審核系統。任務：判斷輸入的評論是否應該被 Flag。"
 "請嚴格輸出 JSON 格式："
 '{"flag": true/false, "reason": "<一句話理由>", "policy_ref": "<簡短規則/要點>", "similar_case_ids": [id1,id2,...]}'
)

def _format_cases(cases):
    # Keep it short for the prompt
    return json.dumps([{"id": c["id"], "label": c["label"], "text": c["text"][:300]} for c in cases], ensure_ascii=False)

def classify_review(text: str, top_k: int = 5):
    cases = retrieve_similar(text, top_k=top_k)
    user_prompt = (
      f'評論：\n"{text}"\n\n'
      f"相似案例（供你參考，不必逐字引用）：\n{_format_cases(cases)}\n\n"
      "請根據平台政策（仇恨/騷擾/人身攻擊/個資洩露/廣告垃圾）判斷是否 Flag。"
      "只輸出 JSON，不要多餘文字。"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":user_prompt}],
        temperature=0
    )
    raw = resp.choices[0].message.content.strip()
    try:
        result = json.loads(raw)
    except Exception:
        # Try to extract JSON substring
        s = raw.find("{")
        e = raw.rfind("}")
        result = json.loads(raw[s:e+1])

    result["similar_cases"] = cases
    return result
