# Title

Expand the product catalog and company search backend

## Suggested GitHub fields

- Labels: `backend`, `catalog`, `api`, `priority: high`
- Assignee: Unassigned
- Milestone: Product catalog MVP

## Issue body

### Goal

Turn the current local demonstration catalog into a scalable product-data layer that can support product-name and company/brand search, product details, label verification, and direct ingredient analysis.

### Current state

The application currently provides a small set of explicitly fictional local test products. They are useful for development but must not be presented as real catalog data.

### Requirements

- Create a durable product catalog model with these fields:
  - Product ID
  - Product name
  - Brand/company name
  - Product category
  - Barcode/GTIN when available
  - Ingredient-label text
  - Product image URL when available
  - Data source
  - Label verification date
  - Last catalog update date
- Support search by:
  - Product name
  - Brand/company name
  - Category
  - Barcode/GTIN
- Support partial matching, exact matching, and clear empty-search results.
- Add product detail endpoints that return the product record and its ingredient label.
- Keep the endpoint that analyzes a selected catalog product using its stored ingredient label.
- Add response metadata that tells the frontend whether the catalog record is demo data, user-provided data, or verified external data.
- Return a clear not-found response when a requested product is unavailable.
- Preserve the current fictional products as development fixtures only, clearly marked as demo records.
- Design the data layer so that a verified third-party product source can be integrated later without changing the frontend API contract.

### Suggested API contract

```text
GET  /api/v1/products?query={product-or-brand}&category={optional}&barcode={optional}
GET  /api/v1/products/{product_id}
POST /api/v1/products/{product_id}/analyze
```

### Out of scope

- Claiming that unknown or unverified labels are accurate
- Product recommendations
- Medical advice or allergy guarantees
- Automatically scraping arbitrary company websites without source/permission review

### Acceptance criteria

- [ ] Product records include all required catalog fields.
- [ ] Search works for a product name and a company/brand name.
- [ ] A barcode query can be accepted and returns a product or a clear not-found result.
- [ ] Product details include ingredient text, source, and verification metadata.
- [ ] The analyze endpoint uses the stored product ingredient label.
- [ ] Demo records are visibly identified as demo data in API responses.
- [ ] Automated API tests cover product search, company search, detail lookup, not-found behavior, and product analysis.
- [ ] Existing ingredient analysis endpoints remain compatible.

### Safety note

Ingredient lists can change. The API must expose when the product label was sourced or verified and should not treat catalog data as a guarantee of the currently sold formulation.
