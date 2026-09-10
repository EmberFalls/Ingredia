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
        applicable = [record for record in evidence if record.is_active and self._applies(record, product_category)]
        # Use the strongest source per concern type so copied sources cannot inflate scores.
        strongest: dict[str, float] = {}
        for record in applicable:
            value = record.severity * record.confidence * 5
            strongest[record.concern_type] = max(strongest.get(record.concern_type, 0), value)
        return min(100, round(sum(strongest.values())))

    def score_product(self, items: list[tuple[str, list[EvidenceRecord]]], product_category: str | None) -> ScoreResult:
        contributors = []
        for canonical_name, evidence in items:
            score = self.ingredient_score(evidence, product_category)
            if score:
                contributors.append({"ingredient": canonical_name, "contribution": score})
        contributors.sort(key=lambda item: int(item["contribution"]), reverse=True)
        # Diminishing contribution means a long label cannot grow without bound.
        total = sum(float(item["contribution"]) / (index + 1) for index, item in enumerate(contributors))
        return ScoreResult(score=min(100, round(total)), contributors=contributors[:5])

    @staticmethod
    def _applies(record: EvidenceRecord, product_category: str | None) -> bool:
        return record.applicability in {"general", "all"} or record.applicability == product_category


def score_band(score: int) -> str:
    if score < 20:
        return "low"
    if score < 50:
        return "moderate"
    return "elevated"
