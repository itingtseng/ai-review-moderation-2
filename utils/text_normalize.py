# -*- coding: utf-8 -*-
# v2025-10-24
"""
text_normalize.py — canonical text normalization / heuristics
這支檔案是 Notebook 外的唯一來源；請在這裡維護最新版。
"""

from __future__ import annotations

import re
import html
import string
import math
from typing import Any, Mapping
from collections import Counter

# -----------------------------
# 基礎常數與 regex（視需要可調）
# -----------------------------
_TEST_TOKENS = {
    "test", "testing", "dummy", "sample", "lorem", "ipsum",
    "asdf", "qwer", "zxcv", "foobar", "foo", "bar"
}
_KEYBOARD_SMASH = re.compile(r"(?:[asdfghjkl]{4,}|[qwertyuiop]{4,}|[zxcvbnm]{4,})", re.I)

# ===========================================================
# ↓↓↓  把你在 01_exploratory_iteration.ipynb 裡找到的最新版
#      函式完整貼進下面五個區塊  ↓↓↓
# ===========================================================
# ====== 若你專案已定義這些，就用你的一版；否則用這些 fallback ======
EXCEPTIONS        = [r"\btest drive\b", r"\bunittest\b", r"\bab test\b"]
HARD_PATTERNS     = [r"\bthis is a test\b", r"\bdummy data\b", r"\blorem ipsum\b", r"\bfoobar\b", r"\btest(?:ing)?\b"]
SOFT_TOKENS       = [r"\basdf\b", r"\bqwer\b", r"\bzxcv\b", r"\bsample\b", r"\bplaceholder\b"]
# test 與測試語境詞在 3 詞距以內（雙向）
NEAR_TEST_CONTEXT     = r"\btest(?:\W+\w+){0,3}\W+(review|example|dummy|sample|placeholder)\b"
NEAR_TEST_CONTEXT_REV = r"\b(review|example|dummy|sample|placeholder)(?:\W+\w+){0,3}\W+test\b"

# 預先編譯（效能佳）
EXC_RE   = [re.compile(p) for p in EXCEPTIONS]
HARD_RE  = [re.compile(p) for p in HARD_PATTERNS]
SOFT_RE  = [re.compile(p) for p in SOFT_TOKENS]
NEAR_FWD = re.compile(NEAR_TEST_CONTEXT)
NEAR_REV = re.compile(NEAR_TEST_CONTEXT_REV)

# --- canonical: normalize_text ---
def normalize_text(s: str) -> str:
    """資料前處理用：HTML 反解、大小寫統一、合併空白（不去標點）。"""
    if not isinstance(s, str):
        return ""
    s = html.unescape(s)
    s = s.casefold().strip()
    s = re.sub(r"\s+", " ", s)
    return s


# --- canonical: is_test_like ---
def is_test_like(s: str) -> bool:
    """判斷是否像測試/假資料字串（HTML 反解、casefold、規則分層）。"""
    if not isinstance(s, str):
        return False

    s_norm = html.unescape(s).casefold().strip()
    if len(s_norm) < 5:
        return False

    # 例外語境：若命中例外且沒有命中硬模板，直接視為非測試
    if any(r.search(s_norm) for r in EXC_RE):
        if not any(r.search(s_norm) for r in HARD_RE):
            return False

    # 硬模板（只要一條命中就算）
    if any(r.search(s_norm) for r in HARD_RE):
        return True

    # 近鄰條件（test 與語境詞 3 詞距內）
    if NEAR_FWD.search(s_norm) or NEAR_REV.search(s_norm):
        return True

    # 軟指標累積（需達門檻）
    soft_hits = sum(bool(r.search(s_norm)) for r in SOFT_RE)
    if soft_hits >= 2:
        return True

    # 併入版本 A 的「超長樣板提示語」規則
    # 偵測平台/表單指示用語 + 很長的字數，常見於測試/說明文字
    if (
        len(s_norm.split()) > 40 and
        "review" in s_norm and
        any(x in s_norm for x in ["describe your", "keep your", "we value", "no personal info"])
    ):
        return True

    return False


# --- canonical: normalize_for_exact ---
def normalize_for_exact(s: str) -> str:
    if not isinstance(s, str): return ""
    s = html.unescape(s)
    s = s.casefold()
    s = s.replace("\u200b", "")        # 去掉零寬字
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --- canonical: normalize_for_near ---
def normalize_for_near(s: str) -> str:
    if not isinstance(s, str): return ""
    s = html.unescape(s)
    s = s.casefold()
    s = re.sub(r"\s+", " ", s)
    # 去標點（讓小差異不影響）
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s


# === Gibberish / Low-quality (v3.1 tuned) ===
MIN_WORDS_KEEP = 2
MAX_WORDS_CUT  = 10000
GIB_THR        = 3      # 覺得太嚴可調 4；太鬆調 2
EMOJI_THR      = 0.30
SYMBOL_THR     = 0.60



# 基本 regex 與輔助
_WORD_RE        = re.compile(r"\b\w+\b", re.UNICODE)
_REPEAT_WORDRE  = re.compile(r"(\b\w+\b)(?:\s+\1){1,}", re.IGNORECASE)
_EMOJI_RE       = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")

# 鍵盤亂壓（含反向）
_LATIN_RUN_RE   = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{32,}")
_ROW_SMASH_RES  = [
    re.compile(r"(?:asdfghjkl){1,}|asdfg|sdfgh|dfghj|fghjk|ghjkl", re.I),
    re.compile(r"(?:qwertyuiop){1,}|qwert|werty|ertyui|rtyuio|tyuiop", re.I),
    re.compile(r"(?:zxcvbnm){1,}|zxcvb|xcvbn|cvbnm", re.I),
    re.compile(r"(?:lkjhg){1,}|lkjhg|kjhgf|jhgf", re.I),
    re.compile(r"(?:ytrewq){1,}|ytrew|trewq", re.I),
    re.compile(r"(?:poiuyt){1,}|poiuy|oiuyt", re.I),
    re.compile(r"(?:mnbvcxz){1,}|mnbvc|nbvcx|bvcxz", re.I),
]
_VOWELS = set(list("aeiouAEIOU") + list("áéíóúÁÉÍÓÚüÜ"))
_REPEAT_CHAR_RE = re.compile(r"(.)\1{3,}", re.UNICODE)         # >=4 重複字元
_CONS_RUN_RE    = re.compile(r"(?i)[bcdfghjklmnpqrstvwxyz]{5,}")
_URL_RE         = re.compile(r"https?://|www\.", re.I)
_EMAIL_RE       = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)

def _safe_str(s) -> str:
    return (s or "").strip()

def _words(s: str) -> list[str]:
    return _WORD_RE.findall(s.lower())

def _char_trigram_entropy(s: str) -> float:
    s = _safe_str(s).lower()
    if len(s) < 10: return 99.0
    trigrams = [s[i:i+3] for i in range(len(s)-2)]
    if not trigrams: return 99.0
    c = Counter(trigrams)
    total = sum(c.values())
    return -sum((n/total) * math.log(n/total + 1e-12, 2) for n in c.values())

def _vowel_ratio(s: str) -> float:
    s = _safe_str(s)
    if not s: return 0.0
    vowels = sum(ch in _VOWELS for ch in s)
    letters= sum(ch.isalpha() for ch in s)
    return vowels / max(1, letters)

def _ratio_emoji(s: str) -> float:
    s = _safe_str(s)
    if not s: return 0.0
    return len(_EMOJI_RE.findall(s)) / len(s)

def _ratio_symbols(s: str) -> float:
    s = _safe_str(s)
    if not s: return 0.0
    total = len(s)
    letters_digits = sum(ch.isalnum() for ch in s)
    spaces = sum(ch.isspace() for ch in s)
    symbols = total - letters_digits - spaces
    return symbols / max(1, total)

def _ratio_url_like(s: str) -> float:
    s = _safe_str(s)
    if not s: return 0.0
    return sum(1 for _ in _URL_RE.finditer(s)) / max(1, len(s.split()))

def _token_has_vowel(tok: str) -> bool:
    return any(ch in _VOWELS for ch in tok)

def gibberish_score_v3(s: str) -> int:
    """
    語言無關結構訊號（無關鍵字名單）：
      +1 詞彙多樣性很低 (unique_ratio < 0.35)
      +1 重複 token
      +1 重複字元（aaaa, !!!!）
      +1 低母音覆蓋（vowel_ratio < 0.25）或長子音連串
      +1 字元三元熵很低（< 2.3）
      +1 超長連續拉丁字母（≥32）
      +1 鍵盤序列片段（含反向）
      +1 emoji 比例過高（> EMOJI_THR）
      +1 符號比例過高（> SYMBOL_THR）
      +1 URL 比例 > 0.4 或含 email 且字數 < 12
      +2 去除非字母後長度 ≥ 60，但僅在「空白極低」或「句末符 ≤ 1」時觸發
      +1 空白比例極低(<2%) 且 字母/數字比例高(>80%)
      +1 存在長無母音 token（> 20）
    """
    if not isinstance(s, str) or not s.strip():
        return 0

    words = _WORD_RE.findall(s)
    if not words:
        return 0

    score = 0

    # 基本訊號
    unique_ratio = len(set(w.lower() for w in words)) / len(words)
    if unique_ratio < 0.35: score += 1

    if _REPEAT_WORDRE.search(s):  score += 1
    if _REPEAT_CHAR_RE.search(s): score += 1
    if _vowel_ratio(s) < 0.25 or _CONS_RUN_RE.search(s): score += 1

    entropy = _char_trigram_entropy(s)
    if entropy < 2.3: score += 1

    if _LATIN_RUN_RE.search(s): score += 1
    if any(r.search(s) for r in _ROW_SMASH_RES): score += 1

    if _ratio_emoji(s) > EMOJI_THR:     score += 1
    if _ratio_symbols(s) > SYMBOL_THR:  score += 1

    url_like = _ratio_url_like(s)
    if url_like > 0.4 or (_EMAIL_RE.search(s) and len(words) < 12):
        score += 1

    # 計算空白/字母數字比例與句末符數
    total = len(s)
    spaces = sum(ch.isspace() for ch in s) if total else 0
    alnum  = sum(ch.isalnum() for ch in s) if total else 0
    space_ratio = (spaces / total) if total else 0.0
    alnum_ratio = (alnum  / total) if total else 0.0
    sent_end_count = len(re.findall(r"[.!?…]+", s))

    # 去除非字母後長度（但避免誤殺正常長文）
    letters_only = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]+", "", s)
    if len(letters_only) >= 60:
        if space_ratio < 0.02 or sent_end_count <= 1:
            score += 2

    # 低空白 + 高字母/數字比例
    if space_ratio < 0.02 and alnum_ratio > 0.80:
        score += 1

    # 長無母音 token
    latin_tokens = [w for w in words if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", w)]
    if any(len(w) > 20 and not _token_has_vowel(w) for w in latin_tokens):
        score += 1

    return max(0, score)

def is_low_quality_v3(row: Mapping[str, Any]) -> bool:
    s  = (row.get("_text_raw") or "")
    wc = int(row.get("_len_words", 0))

    if wc < MIN_WORDS_KEEP:
        return True
    if wc > MAX_WORDS_CUT:
        return True

    # 長文保護：詞數多、母音覆蓋正常、至少兩句 → 放行
    if wc >= 40:
        if _vowel_ratio(s) >= 0.35 and len(re.findall(r"[.!?…]+", s)) >= 2:
            return False

    return gibberish_score_v3(s) >= GIB_THR
