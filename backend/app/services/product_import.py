from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product
from app.providers.products import ProviderProduct


class ProductImportService:
    """Caches normalized provider results in the internal product catalogue."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, item: ProviderProduct) -> Product:
        barcode = item.barcode or item.external_id
        statement = select(Product).where(Product.source_name == item.provider)
        if barcode:
            statement = statement.where(Product.barcode == barcode)
        else:
            statement = statement.where(Product.name == item.name, Product.brand == (item.brand or "Unknown brand"))
        product = self.db.scalar(statement)
        if not product:
            product = Product(name=item.name, brand=item.brand or "Unknown brand", ingredient_text="")
            self.db.add(product)
        product.name = item.name
        product.brand = item.brand or "Unknown brand"
        product.category = item.category
        product.barcode = barcode
        product.ingredient_text = item.ingredient_text or ""
        product.image_url = str(item.image_url) if item.image_url else None
        product.source_type = "public_catalog"
        product.source_name = item.provider
        product.source_url = str(item.product_url) if item.product_url else None
        product.source_confidence = item.source_confidence
        product.source_retrieved_at = datetime.now(timezone.utc)
        product.is_demo = False
        self.db.commit()
        self.db.refresh(product)
        return product
