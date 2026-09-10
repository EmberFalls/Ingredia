from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Product
from app.providers.open_food_facts import OpenFoodFactsProvider
from app.services.product_import import ProductImportService
from app.services.product_search import ProductSearchService


class ProductDiscoveryService:
    """Local-first discovery with a bounded public-catalog fallback."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.local = ProductSearchService(db)
        self.importer = ProductImportService(db)
        self.settings = get_settings()

    async def search(self, *, query: str | None = None, brand: str | None = None, category: str | None = None, barcode: str | None = None, limit: int = 20) -> list[Product]:
        local = self.local.search(query=query, brand=brand, category=category, barcode=barcode, limit=limit)
        if local or not self.settings.product_discovery_external_enabled:
            return local
        provider = OpenFoodFactsProvider()
        if barcode:
            candidate = await provider.get_by_barcode(barcode)
            candidates = [candidate] if candidate else []
        elif query:
            candidates = await provider.search(query, brand=brand, category=category, limit=limit)
        else:
            candidates = []
        return [self.importer.upsert(item) for item in candidates if item]
