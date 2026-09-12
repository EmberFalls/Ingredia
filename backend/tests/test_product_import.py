from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Product
from app.providers.products import ProviderProduct
from app.services.product_import import ProductImportService


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
