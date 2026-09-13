import asyncio

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Product
from app.providers.products import ProviderProduct
from app.services.product_import import ProductImportService
from app.providers.open_food_facts import OpenFoodFactsProvider


def test_import_reconciles_same_barcode_across_providers() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        importer = ProductImportService(session)
        first = importer.upsert(ProviderProduct(
            external_id="12345678", provider="Provider A", name="Original name", brand="Example",
            barcode="12345678", ingredient_text="Water", source_confidence=0.7,
        ))
        second = importer.upsert(ProviderProduct(
            external_id="12345678", provider="Provider B", name="Updated name", brand="Example",
            barcode="12345678", ingredient_text="Water, Milk", source_confidence=0.8,
        ))
        count = session.scalar(select(func.count()).select_from(Product))
    assert first.id == second.id
    assert count == 1
    assert second.source_name == "Provider B"


def test_open_food_facts_prefers_english_product_fields() -> None:
    product = asyncio.run(OpenFoodFactsProvider()._normalize({
        "code": "12345678", "product_name": "Patatas fritas", "product_name_en": "Potato crisps",
        "brands": "Example", "categories": "Aperitivos", "categories_en": "Snacks",
        "ingredients_text": "patatas, sal", "ingredients_text_en": "potatoes, salt",
        "image_front_url": "https://images.openfoodfacts.org/images/products/123/456/78/front_en.1.400.jpg",
        "url": "https://world.openfoodfacts.org/product/12345678", "lang": "es",
    }))
    assert product is not None
    assert product.name == "Potato crisps"
    assert product.category == "Snacks"
    assert product.ingredient_text == "potatoes, salt"


def test_open_food_facts_translates_non_english_product_title() -> None:
    provider = OpenFoodFactsProvider()

    class Translator:
        async def to_english(self, _text: str, _source: str | None) -> str | None:
            return "Potato crisps"

    provider.translator = Translator()
    product = asyncio.run(provider._normalize({
        "code": "12345678", "product_name": "Patatas fritas", "brands": "Example", "lang": "es",
    }))
    assert product is not None
    assert product.name == "Potato crisps"
    assert product.description == "English translation of the provider’s es product title. Original catalog title: Patatas fritas."


def test_open_food_facts_skips_non_english_product_when_translation_fails() -> None:
    provider = OpenFoodFactsProvider()

    class Translator:
        async def to_english(self, _text: str, _source: str | None) -> str | None:
            return None

    provider.translator = Translator()
    product = asyncio.run(provider._normalize({
        "code": "12345678", "product_name": "Patatas fritas", "brands": "Example", "lang": "es",
    }))
    assert product is None
