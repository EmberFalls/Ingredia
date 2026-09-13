"""Small compatibility migrations for the local SQLite development database.

Production deployments should replace this bridge with versioned Alembic
migrations before connecting a shared database.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


PRODUCT_COLUMNS = {
    "barcode": "VARCHAR(32)",
    "source_type": "VARCHAR(40) NOT NULL DEFAULT 'demo'",
    "source_name": "VARCHAR(160) NOT NULL DEFAULT 'Local development catalog'",
    "source_url": "VARCHAR(500)",
    "source_confidence": "FLOAT NOT NULL DEFAULT 0.0",
    "label_verified_at": "DATETIME",
    "source_retrieved_at": "DATETIME",
    "is_demo": "BOOLEAN NOT NULL DEFAULT 1",
}

INGREDIENT_COLUMNS = {
    "normalized_name": "VARCHAR(160)",
    "inci_name": "VARCHAR(160)",
    "cas_number": "VARCHAR(80)",
    "is_active": "BOOLEAN NOT NULL DEFAULT 1",
}

ALIAS_COLUMNS = {
    "alias_type": "VARCHAR(40) NOT NULL DEFAULT 'common_name'",
    "source": "VARCHAR(500)",
    "confidence": "FLOAT NOT NULL DEFAULT 1.0",
}

EVIDENCE_COLUMNS = {
    "source_type": "VARCHAR(80)",
    "evidence_quality": "VARCHAR(40)",
    "jurisdiction": "VARCHAR(80)",
    "exposure_route": "VARCHAR(80)",
    "restriction_condition": "TEXT",
    "retrieved_at": "DATETIME",
}

SCAN_HISTORY_COLUMNS = {
    "product_id": "VARCHAR(36)",
    "product_brand": "VARCHAR(160)",
    "product_image_url": "VARCHAR(500)",
    "product_source_name": "VARCHAR(160)",
    "product_source_type": "VARCHAR(40)",
    "analysis_snapshot": "TEXT",
    "scoring_version": "VARCHAR(80)",
    "evidence_version": "VARCHAR(80)",
}


def apply_local_schema_migrations(engine: Engine) -> None:
    """Keep an existing local SQLite catalog usable as fields are introduced."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    inspector = inspect(engine)
    with engine.begin() as connection:
        tables = set(inspector.get_table_names())
        for table_name, columns in (
            ("ingredients", INGREDIENT_COLUMNS),
            ("ingredient_aliases", ALIAS_COLUMNS),
            ("evidence_records", EVIDENCE_COLUMNS),
        ):
            if table_name in tables:
                existing = {column["name"] for column in inspector.get_columns(table_name)}
                for name, definition in columns.items():
                    if name not in existing:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))
        if "products" in tables:
            existing_products = {column["name"] for column in inspector.get_columns("products")}
            for name, definition in PRODUCT_COLUMNS.items():
                if name not in existing_products:
                    connection.execute(text(f"ALTER TABLE products ADD COLUMN {name} {definition}"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products (barcode)"))
        if "scan_history" in tables:
            existing_history = {column["name"] for column in inspector.get_columns("scan_history")}
            for name, definition in SCAN_HISTORY_COLUMNS.items():
                if name not in existing_history:
                    connection.execute(text(f"ALTER TABLE scan_history ADD COLUMN {name} {definition}"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_scan_history_product_id ON scan_history (product_id)"))
        connection.execute(text("PRAGMA optimize"))
