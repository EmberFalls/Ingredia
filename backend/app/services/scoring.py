from __future__ import annotations

from dataclasses import dataclass

from app.db.models import EvidenceRecord


@dataclass(frozen=True)
class ScoreResult:
    score: int
    contributors: list[dict[str, object]]


class ScoringService:
    """Deterministic evidence-concern score, not a prediction of user harm."""

    def ingredient_score(self, evidence: list[EvidenceRecord], product_category: str | None) -> int:
        applicable = [
            record for record in evidence
            if record.is_active and getattr(record, "source_url", "test-record") and self.applicability_status(record, product_category) in {"direct", "likely"}
        ]
        # Use the strongest source per concern type so copied sources cannot inflate scores.
        strongest: dict[str, float] = {}
        for record in applicable:
            value = record.severity * record.confidence * 5
            strongest[record.concern_type] = max(strongest.get(record.concern_type, 0), value)
        return min(100, round(sum(strongest.values())))

    def ingredient_reasons(self, evidence: list[EvidenceRecord], product_category: str | None) -> list[dict[str, object]]:
        reasons: list[dict[str, object]] = []
        for record in evidence:
            status = self.applicability_status(record, product_category)
            if not record.is_active or not getattr(record, "source_url", "test-record") or status not in {"direct", "likely"}:
                continue
            reasons.append({
                "evidence_id": getattr(record, "id", f"test-{record.concern_type}"),
                "claim_type": record.concern_type,
                "severity": record.severity,
                "confidence": record.confidence,
                "applicability": status,
                "contribution": round(record.severity * record.confidence * 5, 2),
                "source_name": getattr(record, "source_name", "Test evidence"),
                "source_url": getattr(record, "source_url", None),
            })
        return reasons

    def score_product(self, items: list[tuple[str, str, list[EvidenceRecord]] | tuple[str, list[EvidenceRecord]]], product_category: str | None) -> ScoreResult:
        contributors = []
        for item in items:
            ingredient_id, canonical_name, evidence = item if len(item) == 3 else (str(item[0]), str(item[0]), item[1])
            score = self.ingredient_score(evidence, product_category)
            if score:
                contributors.append({
                    "ingredient_id": ingredient_id,
                    "ingredient": canonical_name,
                    "ingredient_score": score,
                    "contribution": score,
                    "reasons": self.ingredient_reasons(evidence, product_category),
                    "evidence_record_ids": [reason["evidence_id"] for reason in self.ingredient_reasons(evidence, product_category)],
                })
        contributors.sort(key=lambda item: int(item["contribution"]), reverse=True)
        # Diminishing contribution means a long label cannot grow without bound.
        total = 0.0
        for index, item in enumerate(contributors):
            weighted = round(float(item["ingredient_score"]) / (index + 1), 2)
            item["contribution"] = weighted
            item["rank"] = index + 1
            total += weighted
        return ScoreResult(score=min(100, round(total)), contributors=contributors)

    @staticmethod
    def applicability_status(record: EvidenceRecord, product_category: str | None) -> str:
        scope = (record.applicability or "general").replace("_", " ").casefold()
        category = (product_category or "").replace("_", " ").casefold()
        if scope in {"general", "all"} or scope == category:
            return "direct"
        if not category:
            return "background"
        food_terms = {"food", "snack", "beverage", "drink", "noodle", "meal", "bakery", "dairy"}
        personal_care_terms = {"personal care", "cosmetic", "skin", "hair", "body", "toiletry"}
        if scope == "food" and any(term in category for term in food_terms):
            return "likely"
        if scope == "personal care" and any(term in category for term in personal_care_terms):
            return "likely"
        return "not_applicable"


def score_band(score: int) -> str:
    if score < 20:
        return "low"
    if score < 50:
        return "moderate"
    return "elevated"
