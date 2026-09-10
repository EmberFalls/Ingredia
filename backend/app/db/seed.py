from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceRecord, Ingredient, IngredientAlias, Product
from app.services.normalizer import normalize_key


SEED_INGREDIENTS = [
    {"name": "Water", "category": "solvent", "description": "Common cosmetic solvent.", "aliases": ["Water", "Aqua", "Aqua (Water)"], "evidence": []},
    {"name": "Glycerin", "category": "humectant", "description": "Common moisture-binding ingredient.", "aliases": ["Glycerin", "Glycerol"], "evidence": []},
    {"name": "Niacinamide", "category": "skin conditioning", "description": "A form of vitamin B3 used in cosmetic formulations.", "aliases": ["Niacinamide", "Nicotinamide"], "evidence": []},
    {"name": "Fragrance", "category": "fragrance", "description": "A fragrance mixture or fragrance-designating label term.", "aliases": ["Fragrance", "Parfum", "Fragrance (Parfum)", "Perfume"], "evidence": [{"concern_type": "sensitization", "severity": 3, "confidence": 0.85, "source_name": "Demo curated evidence", "summary": "Fragrance mixtures can be relevant for people with fragrance sensitivities.", "applicability": "personal_care", "limitations": "Individual ingredients and formulation concentrations are not disclosed by this umbrella label."}]},
    {"name": "Phenoxyethanol", "category": "preservative", "description": "Common cosmetic preservative.", "aliases": ["Phenoxyethanol", "Phenoxethanol"], "evidence": [{"concern_type": "restriction", "severity": 2, "confidence": 0.8, "source_name": "Demo curated evidence", "summary": "Use may be subject to concentration limits depending on jurisdiction and product type.", "applicability": "personal_care", "limitations": "Presence in an ingredient list does not reveal concentration."}]},
    {"name": "Limonene", "category": "fragrance", "description": "Fragrance ingredient found in citrus oils and fragrance compositions.", "aliases": ["Limonene", "d-Limonene"], "evidence": [{"concern_type": "sensitization", "severity": 3, "confidence": 0.82, "source_name": "Demo curated evidence", "summary": "May be relevant for sensitization concerns, especially after oxidation.", "applicability": "personal_care", "limitations": "Risk depends on formulation, oxidation state, and individual sensitivity."}]},
    {"name": "Sodium Benzoate", "category": "preservative", "description": "Common preservative used in food and personal care.", "aliases": ["Sodium Benzoate", "E211", "INS 211"], "evidence": []},
    {"name": "Lecithin", "category": "emulsifier", "description": "Emulsifier commonly used in food and cosmetics.", "aliases": ["Lecithin", "INS 322", "E322"], "evidence": []},
    {"name": "Tartrazine", "category": "colorant", "description": "Synthetic yellow colorant.", "aliases": ["Tartrazine", "CI 19140", "E102", "INS 102"], "evidence": [{"concern_type": "labeling", "severity": 2, "confidence": 0.75, "source_name": "Demo curated evidence", "summary": "Colorant use and labeling can vary by product category and jurisdiction.", "applicability": "all", "limitations": "This record is informational and is not a statement of individual risk."}]},
]

# These are clearly-labelled fictional catalog records. They make the local
# experience testable without presenting unverified real-world label data.
SEED_PRODUCTS = [
    {"name": "Daily Face Cleanser", "brand": "Calmline", "category": "personal_care", "ingredient_text": "Aqua, Glycerin, Niacinamide, Phenoxyethanol", "description": "A gentle, daily-use cleanser."},
    {"name": "Citrus Body Wash", "brand": "Calmline", "category": "personal_care", "ingredient_text": "Aqua, Glycerin, Parfum, Limonene, Phenoxyethanol", "description": "A citrus-scented body wash."},
    {"name": "Color Care Shampoo", "brand": "Calmline", "category": "personal_care", "ingredient_text": "Aqua, Glycerin, Parfum, CI 19140, Limonene", "description": "A color-care shampoo with a fragrance label."},
    {"name": "Lemon Refresher", "brand": "Northstar Pantry", "category": "food", "ingredient_text": "Water, Sugar, Sodium Benzoate (E211), Tartrazine (E102)", "description": "A lemon-flavoured drink."},
    {"name": "Creamy Spread", "brand": "Northstar Pantry", "category": "food", "ingredient_text": "Water, Lecithin (INS 322), Sodium Benzoate", "description": "A plant-based creamy spread."},
]


def seed_database(db: Session) -> None:
    for item in SEED_INGREDIENTS:
        if db.scalar(select(Ingredient.id).where(Ingredient.canonical_name == item["name"])):
            continue
        ingredient = Ingredient(canonical_name=item["name"], category=item["category"], description=item["description"])
        ingredient.aliases = [IngredientAlias(alias=alias, normalized_alias=normalize_key(alias)) for alias in item["aliases"]]
        ingredient.evidence_records = [EvidenceRecord(**record) for record in item["evidence"]]
        db.add(ingredient)
    db.flush()
    for item in SEED_PRODUCTS:
        exists = db.scalar(select(Product.id).where(Product.name == item["name"], Product.brand == item["brand"]))
        if not exists:
            db.add(Product(**item))
    db.commit()
