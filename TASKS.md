# Local product implementation status

- [x] Create FastAPI application, configuration, CORS, health route, and local SQLite setup.
- [x] Create ingredient, alias, evidence, user-preference, and scan-history persistence models.
- [x] Implement manual ingredient-list parsing and deterministic alias/fuzzy normalization.
- [x] Implement explainable, bounded concern scoring and neutral unknown handling.
- [x] Implement text analysis, ingredient search/detail, personal preference matching, and comparison endpoints.
- [x] Add deterministic seed data and unit/API tests.
- [x] Add safe local SQLite schema upgrades for catalog metadata.
- [x] Expand common food/allergen aliases and preserve source-linked evidence records.
- [x] Add saved history, ingredient encounter summaries, item deletion, and clear-history flows.
- [x] Add in-browser Tesseract.js OCR, image cleanup, language choice, and extracted-text review.
- [x] Integrate the user-provided frontend design with analysis, comparison, preference, and ingredient-search API flows.
- [x] Add persistent local accounts, hashed passwords, expiring sessions, and account-data ownership checks.
- [x] Add editable profile photos, dietary context, cultural context, custom requirements, and personal matching.
- [x] Complete catalog product/company/barcode search, image-backed stored products, provenance, analysis, and reporting.
- [x] Verify the frontend production build and lint, plus backend unit/API coverage.

## Intentionally outside this local scope

- Deployment, hosted infrastructure, PostgreSQL, distributed rate limiting, and scale work.
- Google OAuth, which requires provider-issued credentials and configured redirect URLs.
- Medical diagnosis or guarantees about product safety; IngredientIQ remains an explainable label-information tool.
