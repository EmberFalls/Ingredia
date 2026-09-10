from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BrandSource, EvidenceRecord, Ingredient, IngredientAlias, Product
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
    {"name": "Milk", "category": "major food allergen", "description": "Milk and ingredients containing milk protein.", "aliases": ["Milk", "Dairy", "Casein", "Caseinate", "Whey", "Lactalbumin"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Milk is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Label presence does not predict whether or how severely a particular person will react."}]},
    {"name": "Egg", "category": "major food allergen", "description": "Egg and ingredients containing egg protein.", "aliases": ["Egg", "Eggs", "Albumen", "Ovalbumin"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Egg is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Label presence does not predict whether or how severely a particular person will react."}]},
    {"name": "Peanut", "category": "major food allergen", "description": "Peanuts and ingredients containing peanut protein.", "aliases": ["Peanut", "Peanuts", "Groundnut", "Groundnuts", "Arachis oil"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Peanut is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Highly refined oils and regional labeling rules require additional context."}]},
    {"name": "Tree Nut", "category": "major food allergen", "description": "Tree nuts and ingredients containing tree-nut protein.", "aliases": ["Tree Nut", "Tree Nuts", "Almond", "Walnut", "Pecan", "Cashew", "Pistachio", "Hazelnut"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Tree nuts are identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "Specific tree nuts matter; a match to this group is not proof of cross-reactivity."}]},
    {"name": "Wheat", "category": "major food allergen", "description": "Wheat and ingredients containing wheat protein.", "aliases": ["Wheat", "Wheat Flour", "Semolina", "Spelt", "Durum"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Wheat is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Wheat allergy and gluten-related disorders are not interchangeable."}]},
    {"name": "Soybean", "category": "major food allergen", "description": "Soybeans and ingredients containing soy protein.", "aliases": ["Soybean", "Soybeans", "Soy", "Soya", "Soy Protein", "Soya Protein"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Soybean is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Highly refined oils and ingredients with little protein require additional context."}]},
    {"name": "Sesame", "category": "major food allergen", "description": "Sesame and ingredients containing sesame protein.", "aliases": ["Sesame", "Sesame Seed", "Sesame Seeds", "Tahini", "Til", "Gingelly"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.97, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/food/food-allergies/faster-act-sesame-ninth-major-food-allergen", "summary": "Sesame is the ninth major food allergen recognized by U.S. federal law.", "applicability": "food", "limitations": "Requirements and terminology vary by jurisdiction and packaging date."}]},
    {"name": "Fish", "category": "major food allergen", "description": "Finfish and ingredients containing fish protein.", "aliases": ["Fish", "Cod", "Bass", "Flounder", "Salmon", "Tuna"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Fish is identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "The specific fish species should be checked when individual sensitivity is known."}]},
    {"name": "Crustacean Shellfish", "category": "major food allergen", "description": "Crustacean shellfish and ingredients containing their protein.", "aliases": ["Crustacean Shellfish", "Shellfish", "Shrimp", "Prawn", "Crab", "Lobster", "Crayfish"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Crustacean shellfish are identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "Molluscan shellfish are distinct and rules vary by jurisdiction."}]},
]

# These are clearly-labelled fictional catalog records. They make the local
# experience testable without presenting unverified real-world label data.
SEED_PRODUCTS = [
    {"name": "Daily Face Cleanser", "brand": "Calmline", "category": "personal_care", "barcode": "000000000001", "ingredient_text": "Aqua, Glycerin, Niacinamide, Phenoxyethanol", "description": "A gentle, daily-use cleanser.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Citrus Body Wash", "brand": "Calmline", "category": "personal_care", "barcode": "000000000002", "ingredient_text": "Aqua, Glycerin, Parfum, Limonene, Phenoxyethanol", "description": "A citrus-scented body wash.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Color Care Shampoo", "brand": "Calmline", "category": "personal_care", "barcode": "000000000003", "ingredient_text": "Aqua, Glycerin, Parfum, CI 19140, Limonene", "description": "A color-care shampoo with a fragrance label.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Lemon Refresher", "brand": "Northstar Pantry", "category": "food", "barcode": "000000000004", "ingredient_text": "Water, Sugar, Sodium Benzoate (E211), Tartrazine (E102)", "description": "A lemon-flavoured drink.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Creamy Spread", "brand": "Northstar Pantry", "category": "food", "barcode": "000000000005", "ingredient_text": "Water, Lecithin (INS 322), Sodium Benzoate", "description": "A plant-based creamy spread.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
]

SEED_BRAND_SOURCES = [
    {"brand_name": "Calmline", "search_strategy": "MANUAL_ONLY", "enabled": False, "terms_notes": "Fictional development brand; no external site is queried."},
    {"brand_name": "Northstar Pantry", "search_strategy": "MANUAL_ONLY", "enabled": False, "terms_notes": "Fictional development brand; no external site is queried."},
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
        product = db.scalar(select(Product).where(Product.name == item["name"], Product.brand == item["brand"]))
        if not product:
            db.add(Product(**item))
        elif product.is_demo:
            for field, value in item.items():
                setattr(product, field, value)
    for item in SEED_BRAND_SOURCES:
        exists = db.scalar(select(BrandSource.id).where(BrandSource.brand_name == item["brand_name"]))
        if not exists:
            db.add(BrandSource(**item))
    db.commit()
