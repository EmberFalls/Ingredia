from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserProfile
from app.services.normalizer import normalize_key


@dataclass(frozen=True)
class ContextMatch:
    preference_type: str
    message: str


DIET_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "vegan": {
        "animal-derived ingredient": (
            "milk", "whey", "casein", "caseinate", "lactose", "cream", "butter", "cheese",
            "egg", "albumen", "honey", "gelatin", "gelatine", "fish", "shellfish", "lard",
        )
    },
    "vegetarian": {
        "animal-derived ingredient": ("gelatin", "gelatine", "fish", "shellfish", "meat", "lard"),
    },
    "gluten free": {
        "gluten-containing grain": ("wheat", "barley", "rye", "spelt", "semolina", "malt"),
    },
    "dairy free": {
        "milk-derived ingredient": ("milk", "whey", "casein", "caseinate", "lactose", "cream", "butter", "cheese"),
    },
    "egg free": {"egg-derived ingredient": ("egg", "albumen", "ovalbumin")},
}

CULTURAL_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "halal": {"ingredient requiring halal review": ("pork", "lard", "alcohol", "ethanol", "wine", "gelatin", "gelatine")},
    "no pork": {"pork-derived ingredient": ("pork", "lard", "porcine")},
    "kosher": {"ingredient requiring kosher review": ("pork", "lard", "shellfish", "shrimp", "prawn", "crab", "lobster")},
    "jain": {"root vegetable": ("onion", "garlic", "potato", "carrot", "beetroot", "radish", "ginger")},
    "no alcohol": {"alcohol-related ingredient": ("alcohol", "ethanol", "wine", "beer", "rum", "brandy")},
}


class PersonalContextService:
    def __init__(self, db: Session, user_id: str | None) -> None:
        self.profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id)) if user_id else None

    def match(self, raw_token: str, canonical_name: str | None, explicit_preference: str | None) -> ContextMatch | None:
        if explicit_preference:
            return ContextMatch(explicit_preference, f"Matches your configured {explicit_preference} preference.")
        if not self.profile:
            return None
        searchable = normalize_key(f"{raw_token} {canonical_name or ''}")
        for value in self._list(self.profile.dietary_preferences):
            match = self._match_rule(searchable, value, DIET_RULES)
            if match:
                return ContextMatch("diet", f"May conflict with your {value} preference: {match} detected.")
        for value in self._list(self.profile.cultural_considerations):
            match = self._match_rule(searchable, value, CULTURAL_RULES)
            if match:
                return ContextMatch("cultural", f"May need review for your {value} preference: {match} detected.")
        for custom_term in self._additional_terms(self.profile.additional_requirements):
            if self._contains(searchable, custom_term):
                return ContextMatch("additional", f"Matches your additional profile note: {custom_term}.")
        return None

    @staticmethod
    def _list(value: str) -> list[str]:
        try:
            decoded = json.loads(value)
            return [str(item).strip() for item in decoded if str(item).strip()] if isinstance(decoded, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def _match_rule(searchable: str, selected: str, rules: dict[str, dict[str, tuple[str, ...]]]) -> str | None:
        selected_key = normalize_key(selected)
        selected_rules = rules.get(selected_key, {})
        for description, terms in selected_rules.items():
            if any(PersonalContextService._contains(searchable, term) for term in terms):
                return description
        return None

    @staticmethod
    def _additional_terms(value: str | None) -> list[str]:
        if not value:
            return []
        terms = []
        for part in re.split(r"[,;\n]", value):
            cleaned = re.sub(r"^(avoid|no|without|allergic to|sensitive to)\s+", "", part.strip(), flags=re.I)
            key = normalize_key(cleaned)
            if 2 <= len(key) <= 80:
                terms.append(key)
        return terms

    @staticmethod
    def _contains(searchable: str, term: str) -> bool:
        key = normalize_key(term)
        return bool(key and re.search(rf"(?:^|\s){re.escape(key)}(?:$|\s)", searchable))
