# app/decision.py
import re
import yaml
from typing import List, Dict, Any

REASON_LABELS = {
    2: "Off-topic / Irrelevant",
    8: "Promotion / Advertising"
}

class RuleEngine:
    def __init__(self, rules_file: str = "app/rules.yml", alpha: float = 0.6):
        with open(rules_file, "r") as f:
            cfg = yaml.safe_load(f) or {}
        self.rules: List[Dict[str, Any]] = cfg.get("rules", [])
        self.alpha = float(alpha)          # 規則權重
        self.beta = 1.0 - self.alpha       # 相似案例權重（FAISS/LLM 分數）

        for r in self.rules:
            pat = r.get("pattern")
            r["_compiled"] = re.compile(pat, re.IGNORECASE) if pat else None

    def _match_keywords(self, text: str, kws: List[str]) -> List[str]:
        hits = []
        t = text.lower()
        for kw in kws or []:
            if kw.lower() in t:
                hits.append(kw)
        return hits

    def _match_pattern(self, text: str, pattern_obj):
        if not pattern_obj:
            return []
        # 使用 finditer 回傳 Match 物件，避免 findall 在有群組時回 tuple/str
        return [m.group(0) for m in pattern_obj.finditer(text)]

    def rule_scores(self, text: str) -> List[Dict[str, Any]]:
        results = []
        for r in self.rules:
            if not r.get("enabled", True):
                continue
            rid = r.get("id")
            reason_id = r.get("reason_id")
            weight = float(r.get("weight", 0.5))
            kws = r.get("keywords", [])
            creg = r.get("_compiled")

            kw_hits = self._match_keywords(text, kws)
            rgx_hits = self._match_pattern(text, creg)

            hit = bool(kw_hits or rgx_hits)
            score = weight if hit else 0.0

            results.append({
                "id": rid,
                "reason_id": reason_id,
                "reason_label": REASON_LABELS.get(reason_id, str(reason_id)),
                "weight": weight,
                "score": round(score, 3),
                "keyword_hits": kw_hits[:5],
                "regex_hits": rgx_hits[:5],
                "explanation": self._build_expl(reason_id, kw_hits, rgx_hits)
            })
        return results

    def _build_expl(self, reason_id: int, kw_hits: List[str], rgx_hits: List[str]) -> str:
        label = REASON_LABELS.get(reason_id, str(reason_id))
        parts = []
        if kw_hits:
            parts.append(f"關鍵片語：{', '.join(kw_hits[:3])}")
        if rgx_hits:
            parts.append("命中正則：URL/電話/Email/促銷用語")
        if not parts:
            return f"{label}（未命中證據）"
        return f"{label}（" + "；".join(parts) + "）"

    def decide(self, text: str, neighbor_conf: float) -> Dict[str, Any]:
        per_rule = self.rule_scores(text)
        rule_score = sum(r["score"] for r in per_rule)
        rule_score = min(rule_score, 1.0)

        final_score = self.alpha * rule_score + (1.0 - self.alpha) * float(neighbor_conf)
        if final_score >= 0.70:
            risk = "HIGH"
        elif final_score >= 0.40:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        likely_reasons = [
            {"reason_id": r["reason_id"], "reason_label": r["reason_label"], "score": r["score"]}
            for r in per_rule if r["score"] > 0
        ]
        likely_reasons.sort(key=lambda x: x["score"], reverse=True)

        return {
            "alpha": round(self.alpha, 2),
            "beta": round(1.0 - self.alpha, 2),
            "neighbor_conf": round(float(neighbor_conf), 3),
            "rule_score": round(rule_score, 3),
            "final_score": round(final_score, 3),
            "risk_level": risk,
            "rules_detail": per_rule,
            "likely_reasons": likely_reasons[:3]
        }
