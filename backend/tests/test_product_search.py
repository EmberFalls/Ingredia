from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Product
from app.services.product_search import ProductSearchService


def test_search_collapses_package_variants_and_keeps_best_record() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Product(
                name="Doritos Nacho Cheese 150 g",
                brand="Doritos",
                barcode="11111111",
                ingredient_text="",
                source_type="public_catalog",
                source_confidence=0.45,
                image_verification_status="unavailable",
                is_demo=False,
            ),
            Product(
                name="Doritos Nacho Cheese 80 g",
                brand="Doritos",
                barcode="22222222",
                ingredient_text="Corn, vegetable oil, cheese seasoning",
                source_type="official_brand",
                source_confidence=0.95,
                image_verification_status="first_party_record",
                is_demo=False,
            ),
            Product(
                name="Doritos Sweet Chilli 80 g",
                brand="Doritos",
                barcode="33333333",
                ingredient_text="Corn, vegetable oil, sweet chilli seasoning",
                source_type="official_brand",
                source_confidence=0.95,
                image_verification_status="first_party_record",
                is_demo=False,
            ),
        ])
        session.commit()

        products = ProductSearchService(session).search(query="Doritos", limit=20)

    assert [product.barcode for product in products] == ["22222222", "33333333"]
