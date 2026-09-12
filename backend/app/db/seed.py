import json
from html import escape
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BrandSource, EvidenceRecord, Ingredient, IngredientAlias, IngredientFamily, IngredientFamilyMember, Product
from app.services.normalizer import normalize_key


SEED_INGREDIENTS = [
    {"name": "Water", "category": "solvent", "description": "Common cosmetic solvent.", "aliases": ["Water", "Aqua", "Aqua (Water)"], "evidence": []},
    {"name": "Glycerin", "category": "humectant", "description": "Common moisture-binding ingredient.", "aliases": ["Glycerin", "Glycerol"], "evidence": []},
    {"name": "Niacinamide", "category": "skin conditioning", "description": "A form of vitamin B3 used in cosmetic formulations.", "aliases": ["Niacinamide", "Nicotinamide"], "evidence": []},
    {"name": "Fragrance", "category": "fragrance", "description": "A fragrance mixture or fragrance-designating label term.", "aliases": ["Fragrance", "Parfum", "Fragrance (Parfum)", "Perfume"], "evidence": [{"concern_type": "sensitization_context", "severity": 2, "confidence": 0.8, "source_name": "European Chemicals Agency", "source_url": "https://echa.europa.eu/en/hot-topics/skin-sensitising-chemicals", "source_type": "regulatory_authority", "evidence_quality": "regulatory_context", "jurisdiction": "European Union", "exposure_route": "dermal", "summary": "Fragrance-designating terms may conceal individual fragrance substances that are relevant to sensitized users.", "applicability": "personal_care", "limitations": "The umbrella label does not identify the individual fragrance substances or their concentrations."}]},
    {"name": "Phenoxyethanol", "category": "preservative", "description": "Common cosmetic preservative.", "aliases": ["Phenoxyethanol", "Phenoxethanol"], "evidence": [{"concern_type": "regulated_concentration", "severity": 2, "confidence": 0.98, "source_name": "European Commission Scientific Committee on Consumer Safety", "source_url": "https://health.ec.europa.eu/publications/phenoxyethanol_en", "source_type": "expert_regulatory_opinion", "evidence_quality": "high", "jurisdiction": "European Union", "exposure_route": "cosmetic_use", "restriction_condition": "Authorized as a preservative up to 1.0% in ready-for-use cosmetic preparations.", "summary": "The SCCS concluded that phenoxyethanol is safe as a cosmetic preservative at a maximum concentration of 1.0%.", "applicability": "personal_care", "limitations": "Ingredient-list presence does not reveal concentration, so compliance or risk cannot be inferred from presence alone."}]},
    {"name": "Limonene", "category": "fragrance", "description": "Fragrance ingredient found in citrus oils and fragrance compositions.", "aliases": ["Limonene", "d-Limonene"], "evidence": [{"concern_type": "sensitization", "severity": 3, "confidence": 0.95, "source_name": "European Chemicals Agency", "source_url": "https://echa.europa.eu/substance-information/-/substanceinfo/100.025.284", "source_type": "regulatory_substance_database", "evidence_quality": "high", "jurisdiction": "European Union", "exposure_route": "dermal", "summary": "D-limonene is listed in European regulatory substance information and cosmetic restriction context relevant to fragrance sensitization.", "applicability": "personal_care", "limitations": "Product relevance depends on concentration, formulation, oxidation state, route, and individual sensitivity."}]},
    {"name": "Sodium Benzoate", "category": "preservative", "description": "Common preservative used in food and personal care.", "aliases": ["Sodium Benzoate", "E211", "INS 211"], "evidence": []},
    {"name": "Lecithin", "category": "emulsifier", "description": "Emulsifier commonly used in food and cosmetics.", "aliases": ["Lecithin", "INS 322", "E322"], "evidence": []},
    {"name": "Tartrazine", "category": "colorant", "description": "Synthetic yellow colorant.", "aliases": ["Tartrazine", "CI 19140", "E102", "INS 102"], "evidence": [{"concern_type": "labeling", "severity": 2, "confidence": 0.75, "source_name": "Demo curated evidence", "summary": "Colorant use and labeling can vary by product category and jurisdiction.", "applicability": "all", "limitations": "This record is informational and is not a statement of individual risk."}]},
    {"name": "Milk", "category": "major food allergen", "description": "Milk and ingredients containing milk protein.", "aliases": ["Milk", "Dairy", "Casein", "Caseinate", "Whey", "Whey Powder", "Lactalbumin", "Lactose", "Milk Powder", "Skimmed Milk Powder", "Milk Protein", "Cream", "Butter", "Cheese"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Milk is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Label presence does not predict whether or how severely a particular person will react."}]},
    {"name": "Egg", "category": "major food allergen", "description": "Egg and ingredients containing egg protein.", "aliases": ["Egg", "Eggs", "Egg White", "Egg Whites", "Albumen", "Ovalbumin"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Egg is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Label presence does not predict whether or how severely a particular person will react."}]},
    {"name": "Peanut", "category": "major food allergen", "description": "Peanuts and ingredients containing peanut protein.", "aliases": ["Peanut", "Peanuts", "Groundnut", "Groundnuts", "Arachis oil"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Peanut is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Highly refined oils and regional labeling rules require additional context."}]},
    {"name": "Tree Nut", "category": "major food allergen", "description": "Tree nuts and ingredients containing tree-nut protein.", "aliases": ["Tree Nut", "Tree Nuts", "Almond", "Almonds", "Walnut", "Walnuts", "Pecan", "Pecans", "Cashew", "Cashews", "Cashew Nut", "Cashew Nuts", "Pistachio", "Pistachios", "Hazelnut", "Hazelnuts", "Ground Hazelnuts"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Tree nuts are identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "Specific tree nuts matter; a match to this group is not proof of cross-reactivity."}]},
    {"name": "Wheat", "category": "major food allergen", "description": "Wheat and ingredients containing wheat protein.", "aliases": ["Wheat", "Wheat Flour", "Wheat Starch", "Wheat Gluten", "Semolina", "Spelt", "Durum"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Wheat is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Wheat allergy and gluten-related disorders are not interchangeable."}]},
    {"name": "Soybean", "category": "major food allergen", "description": "Soybeans and ingredients containing soy protein.", "aliases": ["Soybean", "Soybeans", "Soy", "Soya", "Soy Protein", "Soya Protein", "Soy Lecithin", "Soy Lecithins", "Soya Lecithin", "Soya Lecithins", "Lecithins [Soya]"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Soybean is identified as a major food allergen under U.S. labeling requirements.", "applicability": "food", "limitations": "Highly refined oils and ingredients with little protein require additional context."}]},
    {"name": "Sesame", "category": "major food allergen", "description": "Sesame and ingredients containing sesame protein.", "aliases": ["Sesame", "Sesame Seed", "Sesame Seeds", "Tahini", "Til", "Gingelly"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.97, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/food/food-allergies/faster-act-sesame-ninth-major-food-allergen", "summary": "Sesame is the ninth major food allergen recognized by U.S. federal law.", "applicability": "food", "limitations": "Requirements and terminology vary by jurisdiction and packaging date."}]},
    {"name": "Fish", "category": "major food allergen", "description": "Finfish and ingredients containing fish protein.", "aliases": ["Fish", "Cod", "Bass", "Flounder", "Salmon", "Tuna"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Fish is identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "The specific fish species should be checked when individual sensitivity is known."}]},
    {"name": "Crustacean Shellfish", "category": "major food allergen", "description": "Crustacean shellfish and ingredients containing their protein.", "aliases": ["Crustacean Shellfish", "Shellfish", "Shrimp", "Prawn", "Crab", "Lobster", "Crayfish"], "evidence": [{"concern_type": "allergen_labeling", "severity": 0, "confidence": 0.95, "source_name": "U.S. Food and Drug Administration", "source_url": "https://www.fda.gov/industry/fda-basics-industry/what-major-food-allergen", "summary": "Crustacean shellfish are identified as a major food-allergen group under U.S. labeling requirements.", "applicability": "food", "limitations": "Molluscan shellfish are distinct and rules vary by jurisdiction."}]},
    {"name": "Sugar", "category": "sweetener", "description": "A common nutritive sweetener.", "aliases": ["Sugar", "Sucrose"], "evidence": []},
    {"name": "Glucose Syrup", "category": "sweetener", "description": "A starch-derived nutritive sweetener.", "aliases": ["Glucose Syrup", "Corn Syrup", "Glucose-Fructose Syrup"], "evidence": []},
    {"name": "Palm Oil", "category": "oil", "description": "An edible plant oil.", "aliases": ["Palm Oil", "Palm Fat"], "evidence": []},
    {"name": "Sunflower Oil", "category": "oil", "description": "An edible plant oil.", "aliases": ["Sunflower Oil"], "evidence": []},
    {"name": "Rapeseed Oil", "category": "oil", "description": "An edible plant oil also called canola oil.", "aliases": ["Rapeseed Oil", "Canola Oil"], "evidence": []},
    {"name": "Cocoa", "category": "food ingredient", "description": "Cocoa-derived ingredient.", "aliases": ["Cocoa", "Low-Fat Cocoa", "Lean Cocoa", "Fat-Reduced Cocoa", "Cocoa Mass", "Chocolate"], "evidence": []},
    {"name": "Citric Acid", "category": "acidity regulator", "description": "A common food acid and acidity regulator.", "aliases": ["Citric Acid", "E330", "INS 330"], "evidence": []},
    {"name": "Salt", "category": "seasoning", "description": "Common edible salt.", "aliases": ["Salt", "Sodium Chloride"], "evidence": []},
    {"name": "Caffeine", "category": "stimulant", "description": "A naturally occurring stimulant used in beverages.", "aliases": ["Caffeine", "Caffeine Flavouring"], "evidence": []},
    {"name": "Carbon Dioxide", "category": "carbonation", "description": "Gas used to carbonate beverages.", "aliases": ["Carbon Dioxide", "E290", "INS 290"], "evidence": []},
    {"name": "Tomato", "category": "food ingredient", "description": "Tomato or tomato-derived ingredient.", "aliases": ["Tomato", "Tomatoes"], "evidence": []},
    {"name": "Vinegar", "category": "food ingredient", "description": "An acidic fermented food ingredient.", "aliases": ["Vinegar", "Alcohol Vinegar"], "evidence": []},
    {"name": "Basil", "category": "herb", "description": "A culinary herb.", "aliases": ["Basil", "Fresh Basil", "Basil Extract"], "evidence": []},
    {"name": "Garlic", "category": "food ingredient", "description": "A culinary allium.", "aliases": ["Garlic"], "evidence": []},
    {"name": "Taurine", "category": "food ingredient", "description": "An amino sulfonic acid used in some beverages.", "aliases": ["Taurine"], "evidence": []},
    {"name": "Vanillin", "category": "flavouring", "description": "A vanilla-associated flavouring compound.", "aliases": ["Vanillin", "Vanilla Extract", "Natural Vanilla Extract"], "evidence": []},
    {"name": "Polytetrafluoroethylene", "category": "film former", "description": "A fluoropolymer also known as PTFE.", "aliases": ["Polytetrafluoroethylene", "PTFE"], "evidence": []},
    {"name": "Gelatin", "category": "animal-derived ingredient", "description": "A protein ingredient derived from collagen.", "aliases": ["Gelatin", "Gelatine"], "evidence": []},
    {"name": "Cooking Wine", "category": "alcohol-related ingredient", "description": "Wine used as a cooking ingredient.", "aliases": ["Cooking Wine", "Wine"], "evidence": []},
    {"name": "Mustard", "category": "food ingredient", "description": "Mustard seed or mustard-derived food ingredient.", "aliases": ["Mustard", "Mustard Seed"], "evidence": []},
]

PFAS_MEMBERSHIPS = json.loads(
    (Path(__file__).resolve().parents[3] / "data" / "seed" / "pfas_memberships.json").read_text(encoding="utf-8")
)

SEED_FAMILIES = [
    {
        "name": "PFAS-related", "slug": "pfas-related",
        "description": "A curated membership based on the OECD PFAS terminology and substance grouping; membership is not itself a product-level risk conclusion.",
        "family_type": "chemical_family", "source_name": "OECD",
        "source_url": "https://www.oecd.org/en/publications/reconciling-terminology-of-the-universe-of-per-and-polyfluoroalkyl-substances_e458e796-en.html",
        "members": [{
            "ingredient": mapping["canonical_ingredient"],
            "relationship_type": mapping["relationship_type"],
            "confidence": mapping["confidence"], "source_name": mapping["source_name"],
            "source_url": mapping["source_url"], "notes": mapping["notes"],
        } for mapping in PFAS_MEMBERSHIPS],
    },
]

# These are clearly-labelled fictional catalog records. They make the local
# experience testable without presenting unverified real-world label data.
SEED_PRODUCTS = [
    {"name": "Daily Face Cleanser", "brand": "Calmline", "category": "personal_care", "barcode": "000000000001", "ingredient_text": "Aqua, Glycerin, Niacinamide, Phenoxyethanol", "description": "A gentle, daily-use cleanser.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Citrus Body Wash", "brand": "Calmline", "category": "personal_care", "barcode": "000000000002", "ingredient_text": "Aqua, Glycerin, Parfum, Limonene, Phenoxyethanol", "description": "A citrus-scented body wash.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Color Care Shampoo", "brand": "Calmline", "category": "personal_care", "barcode": "000000000003", "ingredient_text": "Aqua, Glycerin, Parfum, CI 19140, Limonene", "description": "A color-care shampoo with a fragrance label.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Lemon Refresher", "brand": "Northstar Pantry", "category": "food", "barcode": "000000000004", "ingredient_text": "Water, Sugar, Sodium Benzoate (E211), Tartrazine (E102)", "description": "A lemon-flavoured drink.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {"name": "Creamy Spread", "brand": "Northstar Pantry", "category": "food", "barcode": "000000000005", "ingredient_text": "Water, Lecithin (INS 322), Sodium Benzoate", "description": "A plant-based creamy spread.", "source_type": "demo", "source_name": "Local development catalog", "source_confidence": 0.0, "is_demo": True},
    {
        "name": "Nutella",
        "brand": "Nutella",
        "category": "food",
        "barcode": "3017620422003",
        "ingredient_text": "Sugar, palm oil, hazelnuts 13%, low-fat cocoa 7.4%, skimmed milk powder 6.6%, whey powder, emulsifiers: lecithins [soya], vanillin",
        "image_url": "https://images.openfoodfacts.net/images/products/301/762/042/2003/front_en.883.200.jpg",
        "description": "Cocoa and hazelnut spread.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/3017620422003",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Coca-Cola",
        "brand": "Coca-Cola",
        "category": "food",
        "barcode": "5449000000996",
        "ingredient_text": "Carbonated water, sugar, colour (caramel E150d), acid (phosphoric acid), natural flavourings, caffeine flavouring",
        "image_url": "https://images.openfoodfacts.net/images/products/544/900/000/0996/front_en.1035.200.jpg",
        "description": "Carbonated cola soft drink.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/5449000000996",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Tomato Ketchup",
        "brand": "Heinz",
        "category": "food",
        "barcode": "8715700017006",
        "ingredient_text": "Tomato, alcohol vinegar, sugar, salt, spice extracts, aromatic herb extracts (contains celery), spice",
        "image_url": "https://images.openfoodfacts.net/images/products/871/570/001/7006/front_fr.214.200.jpg",
        "description": "Tomato ketchup.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/8715700017006",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Red Bull Energy Drink",
        "brand": "Red Bull",
        "category": "food",
        "barcode": "9002490100070",
        "ingredient_text": "Water, sucrose, glucose, acidulant (citric acid), carbon dioxide, taurine 0.4%, acidity correctors (sodium carbonates, magnesium carbonates), caffeine 0.03%, vitamins (niacin, pantothenic acid, B6, B12), aromas, colorants (natural caramel, riboflavins)",
        "image_url": "https://images.openfoodfacts.net/images/products/900/249/010/0070/front_en.245.200.jpg",
        "description": "Carbonated energy drink.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/9002490100070",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Natural Mineral Water",
        "brand": "Evian",
        "category": "food",
        "barcode": "3068320120256",
        "ingredient_text": "Natural mineral water",
        "image_url": "https://images.openfoodfacts.net/images/products/306/832/012/0256/front_en.61.200.jpg",
        "description": "Bottled natural mineral water.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/3068320120256",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Pesto alla Genovese",
        "brand": "Barilla",
        "category": "food",
        "barcode": "8076809513753",
        "ingredient_text": "Sunflower oil, fresh basil 30%, cashew nuts, Parmigiano Reggiano PDO cheese 5% (milk), maize fibre, whey powder (milk), salt, milk protein, extra virgin olive oil, sugar, basil extract, natural flavourings (milk), acidity regulator: lactic acid, garlic",
        "image_url": "https://images.openfoodfacts.net/images/products/807/680/951/3753/front_en.347.200.jpg",
        "description": "Basil pesto sauce.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/8076809513753",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Kinder Bueno",
        "brand": "Kinder",
        "category": "food",
        "barcode": "8000500037560",
        "ingredient_text": "Milk chocolate 31.5% (sugar, cocoa butter, cocoa mass, skimmed milk powder, concentrated butter, emulsifiers: lecithins [soya], vanillin), sugar, palm oil, wheat flour, ground hazelnuts 10.8%, skimmed milk powder, milk powder, dark chocolate, lean cocoa, raising agents, salt, vanillin",
        "image_url": "https://images.openfoodfacts.net/images/products/800/050/003/7560/front_en.298.200.jpg",
        "description": "Chocolate-covered hazelnut wafer bar.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/8000500037560",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Philadelphia Original",
        "brand": "Mondelez International",
        "category": "food",
        "barcode": "7622300441937",
        "ingredient_text": "Whole milk, cream, milk protein preparation, concentrated whey permeate, salt, stabilizer (carob seed flour), acidifier (citric acid), pasteurized milk",
        "image_url": "https://images.openfoodfacts.net/images/products/762/230/044/1937/front_en.146.200.jpg",
        "description": "Original cream cheese spread.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/7622300441937",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Oreo Original",
        "brand": "Oreo",
        "category": "food",
        "barcode": "7622300336738",
        "ingredient_text": "Wheat flour, sugar, palm oil, rapeseed oil, wheat starch, low-fat cocoa 4.7%, glucose-fructose syrup, raising agents (ammonium carbonates, potassium carbonates, sodium carbonates), salt, emulsifiers (soy lecithins), acidity regulator (sodium hydroxide), flavourings",
        "image_url": "https://images.openfoodfacts.net/images/products/762/230/033/6738/front_en.407.200.jpg",
        "description": "Chocolate sandwich biscuits with vanilla filling.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/7622300336738",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Snickers",
        "brand": "Snickers",
        "category": "food",
        "barcode": "5000159461122",
        "ingredient_text": "Milk chocolate (sugar, cocoa butter, chocolate, skim milk, lactose, milkfat, soy lecithin), peanuts, corn syrup, sugar, palm oil, skim milk, lactose, salt, egg whites, artificial flavor",
        "image_url": "https://images.openfoodfacts.net/images/products/500/015/946/1122/front_en.311.200.jpg",
        "description": "Chocolate bar with peanuts, caramel, and nougat.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/5000159461122",
        "source_confidence": 0.75,
        "is_demo": False,
    },
    {
        "name": "Twix Twin",
        "brand": "Mars Wrigley",
        "category": "food",
        "barcode": "5000159459228",
        "ingredient_text": "Sugar, glucose syrup, wheat flour 17%, palm fat, cocoa butter, skimmed milk powder, cocoa mass, lactose, milk fat, whey powder (milk), fat-reduced cocoa, salt, emulsifier (soya lecithin), raising agent (E500), natural vanilla extract; may contain hazelnuts and almonds",
        "image_url": "https://images.openfoodfacts.net/images/products/500/015/945/9228/front_en.289.200.jpg",
        "description": "Chocolate-coated caramel biscuit bars.",
        "source_type": "open_food_facts",
        "source_name": "Open Food Facts",
        "source_url": "https://world.openfoodfacts.org/product/5000159459228",
        "source_confidence": 0.75,
        "is_demo": False,
    },
]


DEMO_BRANDS = [
    ("Aster & Field", "#176b5b", "#d9f2e9"),
    ("Bright Table", "#a64f35", "#ffe5d8"),
    ("Cedar & Coast", "#355f8a", "#dcecff"),
    ("Kindred Market", "#765184", "#efe1f3"),
    ("Morrow Goods", "#7d6428", "#f6e9b9"),
    ("Northlight", "#285a55", "#d7ece7"),
    ("Willow House", "#8a5260", "#f6dfe5"),
]

DEMO_PRODUCT_TEMPLATES = [
    ("Oat Crunch Cereal", "food", "Wheat flour, sugar, sunflower oil, salt", "A crisp breakfast cereal with a short sample label."),
    ("Cocoa Hazelnut Bites", "food", "Sugar, wheat flour, cocoa, hazelnuts, milk powder, soy lecithin", "Cocoa snack bites with declared milk, soy, wheat, and tree nuts."),
    ("Tomato Basil Sauce", "food", "Tomato, sunflower oil, sugar, salt, basil, garlic", "A tomato and herb cooking sauce."),
    ("Lemon Sparkling Drink", "food", "Carbonated water, sugar, citric acid, sodium benzoate", "A carbonated lemon-flavoured sample drink."),
    ("Vanilla Wafer", "food", "Wheat flour, sugar, palm oil, milk powder, egg whites, vanillin", "A crisp vanilla wafer with declared wheat, milk, and egg."),
    ("Creamy Herb Dip", "food", "Milk, cream, sunflower oil, salt, basil, garlic", "A chilled dairy and herb sample dip."),
    ("Sesame Crackers", "food", "Wheat flour, sesame seeds, sunflower oil, sugar, salt", "Oven-baked sample crackers with sesame and wheat."),
    ("Peanut Energy Bar", "food", "Peanuts, glucose syrup, cocoa, milk powder, soy lecithin", "A sample snack bar with declared peanut, milk, and soy."),
    ("Daily Gel Cleanser", "personal_care", "Aqua, glycerin, niacinamide, phenoxyethanol", "A gentle sample facial cleanser."),
    ("Citrus Hand Wash", "personal_care", "Aqua, glycerin, parfum, limonene, phenoxyethanol", "A citrus-scented sample hand wash."),
    ("Hydrating Body Lotion", "personal_care", "Aqua, glycerin, niacinamide, parfum, phenoxyethanol", "A moisturising sample body lotion."),
    ("Fragrance-Free Shampoo", "personal_care", "Aqua, glycerin, niacinamide, sodium benzoate", "A fragrance-free sample shampoo."),
]


def _demo_package_image(brand: str, product: str, foreground: str, background: str) -> str:
    initials = "".join(word[0] for word in brand.split() if word[0].isalnum())[:2].upper()
    short_name = product if len(product) <= 22 else f"{product[:21]}…"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="260" viewBox="0 0 320 260">'
        f'<rect width="320" height="260" rx="28" fill="{background}"/>'
        f'<circle cx="160" cy="82" r="42" fill="{foreground}"/>'
        f'<text x="160" y="94" text-anchor="middle" font-family="Arial" font-size="30" font-weight="700" fill="white">{escape(initials)}</text>'
        f'<text x="160" y="155" text-anchor="middle" font-family="Arial" font-size="16" font-weight="700" fill="{foreground}">{escape(brand)}</text>'
        f'<text x="160" y="184" text-anchor="middle" font-family="Arial" font-size="14" fill="#263b36">{escape(short_name)}</text>'
        f'<text x="160" y="220" text-anchor="middle" font-family="Arial" font-size="11" fill="#59736c">DEMO LABEL</text>'
        '</svg>'
    )
    return f"data:image/svg+xml,{quote(svg, safe='')}"


def expanded_demo_products() -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    for brand_index, (brand, foreground, background) in enumerate(DEMO_BRANDS, start=1):
        for product_index, (name, category, ingredients, description) in enumerate(DEMO_PRODUCT_TEMPLATES, start=1):
            products.append({
                "name": name,
                "brand": brand,
                "category": category,
                "barcode": f"990{brand_index:02d}{product_index:02d}000000",
                "ingredient_text": ingredients,
                "image_url": _demo_package_image(brand, name, foreground, background),
                "description": description,
                "source_type": "demo",
                "source_name": "Local development catalog",
                "source_confidence": 0.0,
                "is_demo": True,
            })
    return products


CATALOG_DATA_PATH = Path(__file__).with_name("official_product_catalog.json")


def _load_real_catalog() -> list[dict[str, object]]:
    """Load the checked-in, first-party official product catalog snapshot."""
    records = json.loads(CATALOG_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) < 100:
        raise RuntimeError("The real product catalog must contain at least 100 records.")
    required = {"name", "brand", "barcode", "ingredient_text", "image_url", "source_url"}
    if any(not isinstance(item, dict) or not required.issubset(item) for item in records):
        raise RuntimeError("The real product catalog contains an incomplete product record.")
    return records


# A static snapshot makes the app usable offline. Every entry has a first-party
# product page, exact ingredient label, UPC/GTIN, and official package image.
SEED_PRODUCTS = _load_real_catalog()
SEED_BRAND_SOURCES = [
    {
        "brand_name": str(product["brand"]),
        "search_strategy": "MANUAL_ONLY",
        "enabled": False,
        "terms_notes": "Brand product data sourced from its official Snackworks product page.",
    }
    for product in SEED_PRODUCTS
]


def seed_database(db: Session) -> None:
    for item in SEED_INGREDIENTS:
        ingredient = db.scalar(select(Ingredient).where(Ingredient.canonical_name == item["name"]))
        if not ingredient:
            ingredient = Ingredient(canonical_name=item["name"], normalized_name=normalize_key(item["name"]), category=item["category"], description=item["description"])
            db.add(ingredient)
            db.flush()
        else:
            ingredient.normalized_name = normalize_key(item["name"])
            ingredient.is_active = True
        for record_data in item["evidence"]:
            record = next((row for row in ingredient.evidence_records if row.concern_type == record_data["concern_type"]), None)
            if not record:
                ingredient.evidence_records.append(EvidenceRecord(**record_data))
            else:
                for field, value in record_data.items():
                    setattr(record, field, value)
        existing_aliases = {alias.normalized_alias for alias in ingredient.aliases}
        for alias in item["aliases"]:
            normalized = normalize_key(alias)
            if normalized not in existing_aliases:
                ingredient.aliases.append(IngredientAlias(alias=alias, normalized_alias=normalized, alias_type="common_name", source="Curated Ingredia seed"))
                existing_aliases.add(normalized)
    db.flush()
    for family_data in SEED_FAMILIES:
        family = db.scalar(select(IngredientFamily).where(IngredientFamily.slug == family_data["slug"]))
        family_fields = {key: value for key, value in family_data.items() if key != "members"}
        if not family:
            family = IngredientFamily(**family_fields)
            db.add(family)
            db.flush()
        else:
            for field, value in family_fields.items():
                setattr(family, field, value)
        for member_data in family_data["members"]:
            ingredient = db.scalar(select(Ingredient).where(Ingredient.canonical_name == member_data["ingredient"]))
            if not ingredient:
                continue
            membership = db.scalar(select(IngredientFamilyMember).where(
                IngredientFamilyMember.family_id == family.id,
                IngredientFamilyMember.ingredient_id == ingredient.id,
            ))
            values = {key: value for key, value in member_data.items() if key != "ingredient"}
            if not membership:
                db.add(IngredientFamilyMember(family_id=family.id, ingredient_id=ingredient.id, **values))
            else:
                for field, value in values.items():
                    setattr(membership, field, value)
    # Replace earlier demo and community-photo seed records on upgrade. Saved
    # analyses retain their denormalized product text and provenance.
    retired_sources = ("demo", "open_food_facts", "public_catalog")
    for product in db.scalars(
        select(Product).where(
            (Product.is_demo.is_(True)) | (Product.source_type.in_(retired_sources))
        )
    ).all():
        db.delete(product)
    for source in db.scalars(
        select(BrandSource).where(BrandSource.terms_notes.ilike("%fictional%"))
    ).all():
        db.delete(source)
    db.flush()
    for item in SEED_PRODUCTS:
        product = db.scalar(select(Product).where(Product.name == item["name"], Product.brand == item["brand"]))
        if not product:
            db.add(Product(**item))
        else:
            for field, value in item.items():
                setattr(product, field, value)
    for item in SEED_BRAND_SOURCES:
        exists = db.scalar(select(BrandSource.id).where(BrandSource.brand_name == item["brand_name"]))
        if not exists:
            db.add(BrandSource(**item))
    db.commit()
