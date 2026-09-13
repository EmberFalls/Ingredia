from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Product
from app.providers.open_food_facts import OpenFoodFactsProvider, ProductProviderUnavailable
from app.services.product_import import ProductImportService
from app.services.product_search import ProductSearchService


class ProductDiscoveryService:
    """Local-first discovery with a bounded public-catalog fallback."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.local = ProductSearchService(db)
        self.importer = ProductImportService(db)
        self.settings = get_settings()

    async def search(self, *, query: str | None = None, brand: str | None = None, category: str | None = None, barcode: str | None = None, limit: int = 20) -> tuple[list[Product], str]:
        local = self.local.search(query=query, brand=brand, category=category, barcode=barcode, limit=limit)
        # Checked-in official records are stable. Public-catalog records are a
        # cache, however, and must be refreshed so older translated-or-not
        # provider payloads cannot keep resurfacing ahead of the English-only
        # normalization rule.
        # Listing or filtering an already-populated catalog should always be
        # useful offline. Only a specific product query/barcode lookup needs
        # the external refresh path for public-cache records.
        external_lookup_requested = bool(query or barcode)
        if local and (
            not external_lookup_requested
            or any(product.source_type != "public_catalog" for product in local)
        ):
            return local, "local_match"
        if not self.settings.product_discovery_external_enabled:
            return local, "local_match" if local else "no_match"
        provider = OpenFoodFactsProvider()
        try:
            if barcode:
                candidate = await provider.get_by_barcode(barcode)
                candidates = [candidate] if candidate else []
            elif query:
                candidates = await provider.search(query, brand=brand, category=category, limit=limit)
            else:
                candidates = []
        except ProductProviderUnavailable:
            return [], "external_unavailable"
        products = [self.importer.upsert(item) for item in candidates if item]
        return products, "external_match" if products else "no_match"
