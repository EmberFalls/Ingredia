"""Import at least 100 image-backed popular Indian products into the local catalog.

Run from the backend directory with the project's Python environment. Records
are sourced from Open Food Facts, barcode-linked, and deliberately marked as
provider catalog images rather than first-party manufacturer verification.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db.database import Base, SessionLocal, engine
from app.db.migrations import apply_local_schema_migrations
from app.db.seed import seed_database
from app.db.models import Product
from app.providers.open_food_facts import OpenFoodFactsProvider, ProductProviderUnavailable
from app.services.product_import import ProductImportService


async def main() -> None:
    Base.metadata.create_all(bind=engine)
    apply_local_schema_migrations(engine)
    with SessionLocal() as db:
        seed_database(db)
        try:
            # Ask for a small buffer because public catalogs can contain a
            # few same-name package variants that reconcile to one local row.
            products = await OpenFoodFactsProvider().popular_in_india(120)
        except ProductProviderUnavailable as error:
            raise SystemExit(f"The public catalog could not be reached: {error}") from error
        importer = ProductImportService(db)
        for product in products:
            importer.upsert(product)
        stored = db.scalar(
            select(func.count()).select_from(Product).where(Product.catalog_market == "India")
        )
        print(f"Imported {len(products)} provider records; {stored} Popular in India products are stored locally.")


if __name__ == "__main__":
    asyncio.run(main())
