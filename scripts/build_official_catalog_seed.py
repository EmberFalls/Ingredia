"""Build the local catalog from first-party Snackworks product pages.

Each accepted record must expose, on the same official product page:
- a product-specific heading;
- an exact ingredient statement;
- a UPC/GTIN;
- a manufacturer-supplied package image.

The resulting snapshot is checked in so ordinary local startup does not crawl
the public website or depend on its availability.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SITEMAP_URL = "https://www.snackworks.com/sitemap-pages.xml"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "backend" / "app" / "db" / "official_product_catalog.json"
TARGET_COUNT = 100
USER_AGENT = "Ingredia/0.1 (official product catalog collector)"
ALLOWED_IMAGE_HOSTS = {"images.salsify.com", "www.snackworks.com", "snackworks.com"}
KNOWN_BRANDS = (
    "CHICKEN IN A BISKIT",
    "BETTER CHEDDARS",
    "FLAVOR ORIGINALS",
    "LORNA DOONE",
    "GOOD THINS",
    "EASY CHEESE",
    "CHIPS AHOY!",
    "SOUR PATCH KIDS",
    "WHEAT THINS",
    "TATE'S BAKE SHOP",
    "HONEY MAID",
    "NUTTER BUTTER",
    "SWEDISH FISH",
    "SOUR PUNCH",
    "CLIF BAR",
    "PERFECT SNACKS",
    "ENJOY LIFE",
    "NILLA",
    "HALLS",
    "DENTYNE",
    "BISCOS",
    "BARNUM'S",
    "HANDI-SNACKS",
    "MALLOMARS",
    "NEWTONS",
    "PINWHEELS",
    "NABISCO",
    "LU",
    "7DAYS",
    "BELVITA",
    "CADBURY",
    "OREO",
    "RITZ",
    "TRISCUIT",
    "PREMIUM",
    "TRIDENT",
)


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed first-party URLs
        return response.read().decode("utf-8", errors="replace")


def clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = unescape(without_tags).replace("\xa0", " ").replace("\u200b", "").replace("\u200c", "")
    return " ".join(normalized.split())


def meta_content(markup: str, key: str) -> str:
    patterns = (
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, markup, flags=re.IGNORECASE)
        if match:
            return clean_html(match.group(1))
    return ""


def brand_for(name: str) -> str:
    upper_name = name.upper()
    for brand in KNOWN_BRANDS:
        if upper_name.startswith(brand):
            display_names = {
                "BELVITA": "belVita",
                "CHIPS AHOY!": "CHIPS AHOY!",
                "7DAYS": "7DAYS",
                "OREO": "OREO",
                "RITZ": "RITZ",
            }
            return display_names.get(brand, brand.title())
    return name.split()[0].strip("®™!,:-")


def parse_product(url: str) -> dict[str, object] | None:
    try:
        markup = fetch(url)
    except Exception:
        return None

    heading_match = re.search(r"<h1[^>]*>(.*?)</h1>", markup, flags=re.IGNORECASE | re.DOTALL)
    ingredient_match = re.search(r"INGREDIENTS:\s*(.*?)</p>", markup, flags=re.IGNORECASE | re.DOTALL)
    upc_match = re.search(r'data-sc-upc=["\']([0-9]{8,14})["\']', markup, flags=re.IGNORECASE)
    if not upc_match:
        upc_match = re.search(r"smtlbl\.app/upc/([0-9]{8,14})", markup, flags=re.IGNORECASE)
    image_url = meta_content(markup, "og:image") or meta_content(markup, "og:image:url")
    name = clean_html(heading_match.group(1)) if heading_match else ""
    ingredients = clean_html(ingredient_match.group(1)) if ingredient_match else ""
    barcode = upc_match.group(1) if upc_match else ""
    image_host = (urlparse(image_url).hostname or "").lower()
    if not all((name, ingredients, barcode, image_url)) or image_host not in ALLOWED_IMAGE_HOSTS:
        return None
    if len(name) > 160 or len(barcode) > 32:
        return None

    return {
        "name": name,
        "brand": brand_for(name),
        "category": "packaged_food",
        "barcode": barcode,
        "ingredient_text": ingredients,
        "image_url": image_url,
        "description": "Official package image and ingredient label from the brand's Snackworks product page.",
        "source_type": "official_brand",
        "source_name": "Snackworks official product catalog",
        "source_url": url,
        "source_confidence": 0.98,
        "is_demo": False,
    }


def product_urls() -> list[str]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>(https?://(?:www\.)?snackworks\.com/products/[^<]+)</loc>", sitemap, flags=re.IGNORECASE)
    return sorted({unescape(url) for url in urls if "/index.html" not in url})


def main() -> None:
    urls = product_urls()
    records: list[dict[str, object]] = []
    seen_barcodes: set[str] = set()
    seen_products: set[tuple[str, str]] = set()
    with ThreadPoolExecutor(max_workers=24) as executor:
        futures = {executor.submit(parse_product, url): url for url in urls[:240]}
        for future in as_completed(futures):
            record = future.result()
            if not record:
                continue
            barcode = str(record["barcode"])
            key = (str(record["name"]).casefold(), str(record["brand"]).casefold())
            if barcode in seen_barcodes or key in seen_products:
                continue
            seen_barcodes.add(barcode)
            seen_products.add(key)
            records.append(record)

    records.sort(key=lambda record: (str(record["brand"]).casefold(), str(record["name"]).casefold()))
    if len(records) < TARGET_COUNT:
        raise RuntimeError(f"Only {len(records)} fully verified official products were found.")

    # Round-robin across brands so the catalog is useful and visually varied,
    # instead of filling the first 100 slots alphabetically from a few brands.
    by_brand: dict[str, deque[dict[str, object]]] = defaultdict(deque)
    for record in records:
        by_brand[str(record["brand"])].append(record)
    selected: list[dict[str, object]] = []
    while len(selected) < TARGET_COUNT:
        added = False
        for brand in sorted(by_brand, key=str.casefold):
            if by_brand[brand]:
                selected.append(by_brand[brand].popleft())
                added = True
                if len(selected) == TARGET_COUNT:
                    break
        if not added:
            break

    OUTPUT_PATH.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(selected)} official product records from {len({item['brand'] for item in selected})} brands to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
