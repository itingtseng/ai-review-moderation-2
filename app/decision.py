# app/decision.py
import re
import yaml
from typing import List, Dict, Any

REASON_LABELS = {
    1: "Wrong Community",
    2: "Off-topic / Irrelevant",
    3: "False Information",
    4: "Affiliated with Community",
    5: "Competitor / Ex-employee",
    6: "Toxic / Hate Speech",
    7: "Privacy Violation",
    8: "Promotion / Advertising",
    9: "COVID Misinformation"
}

# These four reasons cannot be verified automatically — route to human review
HITL_REASONS = {1, 3, 4, 5}

# Detect two or more consecutive capitalized words (possible name or community name)
PROPER_NOUN_PATTERN = re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)')


class RuleEngine:
    def __init__(self, rules_file: str = "app/rules.yml", alpha: float = 0.6):
        with open(rules_file, "r") as f:
            cfg = yaml.safe_load(f) or {}
        self.rules: List[Dict[str, Any]] = cfg.get("rules", [])
        self.alpha = float(alpha)
        self.beta = 1.0 - self.alpha

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
        return [m.group(0) for m in pattern_obj.finditer(text)]

    def _unique_hits(self, hits: List[str]) -> List[str]:
        """Remove duplicate evidence while preserving the order it was found."""
        seen = set()
        unique = []
        for hit in hits:
            key = hit.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(hit)
        return unique

    def _detect_proper_nouns(self, text: str) -> List[str]:
        """Detect possible names or community names (2+ consecutive capitalized words)"""
        matches = PROPER_NOUN_PATTERN.findall(text)
        # Filter out common false positives
        ignore = {"I Am", "I Have", "I Was", "I Will", "I Would", "I Can",
                  "New York", "Los Angeles", "San Francisco", "United States"}
        return [m for m in matches if m not in ignore]

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
            pattern_label = r.get("pattern_label")

            kw_hits = self._match_keywords(text, kws)
            rgx_hits = self._match_pattern(text, creg)
            matched_phrases = self._unique_hits(kw_hits + rgx_hits)

            hit = bool(kw_hits or rgx_hits)
            score = weight if hit else 0.0
            requires_hitl = reason_id in HITL_REASONS

            results.append({
                "id": rid,
                "reason_id": reason_id,
                "reason_label": REASON_LABELS.get(reason_id, str(reason_id)),
                "weight": weight,
                "score": round(score, 3),
                "keyword_hits": kw_hits[:5],
                "regex_hits": rgx_hits[:5],
                "matched_phrases": matched_phrases[:8],
                "detected_pattern": pattern_label if rgx_hits else None,
                "requires_human_review": requires_hitl,
                "explanation": self._build_expl(reason_id, kw_hits, rgx_hits, requires_hitl)
            })
        return results

    def _build_expl(self, reason_id: int, kw_hits: List[str], rgx_hits: List[str], requires_hitl: bool) -> str:
        label = REASON_LABELS.get(reason_id, str(reason_id))
        parts = []
        if kw_hits:
            parts.append(f"Matched phrases: {', '.join(kw_hits[:3])}")
        if rgx_hits:
            parts.append(f"Detected text pattern: {', '.join(self._unique_hits(rgx_hits)[:3])}")
        if not parts:
            return f"{label} (no matching evidence)"
        note = " — requires human review" if requires_hitl else ""
        return f"{label} (" + "; ".join(parts) + ")" + note

    def decide(self, text: str, neighbor_conf: float) -> Dict[str, Any]:
        per_rule = self.rule_scores(text)
        rule_score = sum(r["score"] for r in per_rule)
        rule_score = min(rule_score, 1.0)

        triggered_count = sum(
    1 for rule in per_rule
    if rule["score"] > 0
)

        weighted_score = (
            self.alpha * rule_score
            + (1.0 - self.alpha) * float(neighbor_conf)
        )

        multi_signal_boost = 0.10 * max(0, triggered_count - 1)

        final_score = min(
            0.95,
            weighted_score + multi_signal_boost,
        )
        final_score = max(rule_score, weighted_score)
        if final_score >= 0.70:
            risk = "HIGH"
        elif final_score >= 0.40:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        likely_reasons = [
            {
                "reason_id": r["reason_id"],
                "reason_label": r["reason_label"],
                "score": r["score"],
                "requires_human_review": r["requires_human_review"]
            }
            for r in per_rule if r["score"] > 0
        ]
        likely_reasons.sort(key=lambda x: x["score"], reverse=True)

        # HITL: if any triggered reason is unverifiable
        requires_human_review = any(
            r["reason_id"] in HITL_REASONS and r["score"] > 0
            for r in per_rule
        )

        # Proper noun detection
        proper_nouns = self._detect_proper_nouns(text)
        proper_noun_warning = None
        if proper_nouns:
            proper_noun_warning = (
                f"This review may contain names or community references "
                f"({', '.join(proper_nouns[:3])}). "
                f"Please verify manually."
            )

        return {
            "alpha": round(self.alpha, 2),
            "beta": round(1.0 - self.alpha, 2),
            "neighbor_conf": round(float(neighbor_conf), 3),
            "rule_score": round(rule_score, 3),
            "final_score": round(final_score, 3),
            "risk_level": risk,
            "requires_human_review": requires_human_review,
            "proper_noun_warning": proper_noun_warning,
            "rules_detail": per_rule,
            "likely_reasons": likely_reasons[:3]
        }
