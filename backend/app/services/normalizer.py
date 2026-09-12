from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Ingredient, IngredientAlias


@dataclass(frozen=True)
class NormalizedIngredient:
    ingredient: Ingredient | None
    method: str
    confidence: float


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class IngredientNormalizer:
    def __init__(self, db: Session, fuzzy_threshold: float = 0.88) -> None:
        self.db = db
        self.fuzzy_threshold = fuzzy_threshold

    def normalize(self, raw_token: str) -> NormalizedIngredient:
        candidates = self._candidate_forms(raw_token)
        aliases = self.db.scalars(select(IngredientAlias).join(IngredientAlias.ingredient)).all()
        by_key = {alias.normalized_alias: alias for alias in aliases}
        for candidate in candidates:
            alias = by_key.get(normalize_key(candidate))
            if alias:
                method = "exact_canonical" if normalize_key(alias.alias) == normalize_key(alias.ingredient.canonical_name) else "exact_alias"
                return NormalizedIngredient(alias.ingredient, method, 1.0)
        best_alias: IngredientAlias | None = None
        best_score = 0.0
        for candidate in candidates:
            key = normalize_key(candidate)
            for alias in aliases:
                score = SequenceMatcher(None, key, alias.normalized_alias).ratio()
                if score > best_score:
                    best_alias, best_score = alias, score
        if best_alias and best_score >= self.fuzzy_threshold:
            return NormalizedIngredient(best_alias.ingredient, "fuzzy_alias", round(best_score, 3))
        return NormalizedIngredient(None, "unknown", 0.0)

    @staticmethod
    def _candidate_forms(raw_token: str) -> list[str]:
        forms = [raw_token]
        without_percent = re.sub(r"\s*\d+(?:\.\d+)?\s*%\s*$", "", raw_token).strip()
        if without_percent != raw_token:
            forms.append(without_percent)
        if ":" in without_percent:
            forms.append(without_percent.rsplit(":", 1)[1].strip())
        without_quantity = re.sub(r"\s+\d+(?:\.\d+)?\s*%?\s*$", "", without_percent).strip()
        if without_quantity and without_quantity != without_percent:
            forms.append(without_quantity)
        for part in re.split(r"\s*/\s*", without_percent):
            if part:
                forms.append(part)
        parenthetical = re.search(r"\(([^)]+)\)", without_percent)
        if parenthetical:
            forms.append(parenthetical.group(1))
            forms.append(re.sub(r"\s*\([^)]+\)", "", without_percent).strip())
        return list(dict.fromkeys(form for form in forms if form))
