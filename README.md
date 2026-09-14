# Ingredient Intelligence Platform

Complete local-first web product for transparent ingredient-list analysis. It parses pasted or OCR-extracted labels, resolves aliases and nested constituents, returns source-linked evidence, creates a deterministic evidence-concern score, and keeps personal alerts separate from that general score.

Ingredia now exposes its full auditable novelty chain: raw label terms resolve to canonical identities with resolved/uncertain/unknown states; verified family memberships remain source-backed; analysis coverage and evidence-linked score contributions are explicit; catalogue, pasted, and OCR inputs retain provenance; personal matches remain parallel to the general score; saved analyses produce repeated-ingredient encounter insights; and comparisons explain their score differences deterministically.

The included frontend is configured to run locally at `http://localhost:3000` and connect to this API.

## Frontend

The React frontend lives in `frontend/`. It provides account creation and login, guided onboarding, in-browser label OCR, catalog and barcode search, evidence detail, editable profiles and preferences, saved history, product comparison, and catalog-data reporting.

```powershell
cd frontend
pnpm dev
```

The frontend expects the API at `http://127.0.0.1:8000/api/v1` by default. Set `NEXT_PUBLIC_API_BASE_URL` to point at another API instance.

## Run locally

```powershell
cd backend
# Use Python 3.11–3.13. A virtual environment prevents incompatible global
# packages from affecting the API or its tests.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation. The application creates and seeds a local SQLite database on startup.

## Test

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

## Implemented API

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/analyses/text`
- `GET /api/v1/ingredients?query=...`
- `GET /api/v1/ingredients/{ingredient_id}`
- `GET /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `POST /api/v1/products/{product_id}/analyze`
- `POST /api/v1/products/{product_id}/reports`
- `PUT /api/v1/users/{user_id}/preferences`
- `GET /api/v1/users/{user_id}/preferences`
- `DELETE /api/v1/users/{user_id}/preferences/{ingredient_id}`
- `GET|PUT /api/v1/users/{user_id}/profile`
- `GET /api/v1/users/{user_id}/history`
- `GET /api/v1/users/{user_id}/insights/ingredients?days=7|30`
- `DELETE /api/v1/users/{user_id}/history/{history_id}`
- `DELETE /api/v1/users/{user_id}/history`
- `POST /api/v1/comparisons`

Passwords are salted and hashed with PBKDF2-SHA256. Random 30-day bearer sessions are stored as hashes, and persisted account data is protected by matching-session checks. API responses include request IDs, conservative security headers, and a configurable local rate limit. Catalog imports reconcile matching barcodes across providers, and catalog records retain source and retrieval metadata.

The seeded catalog contains 100 packaged-food records collected from official Snackworks product pages. Every record includes a manufacturer-supplied package image, UPC/GTIN, exact ingredient label, and first-party provenance URL. External Open Food Facts discovery remains available for uncached searches, while the default stored catalog uses only the curated official records. Product labels can change; the UI exposes provenance and a report-data flow.

OCR runs in the browser with Tesseract.js. The selected language data may be fetched the first time that language is used; recognized text is shown for review before analysis.

## Local-product boundary

This repository is intentionally complete for local use, not deployment or multi-instance scale. It uses SQLite, local email/password accounts, and a browser-stored session token. Google sign-in is intentionally not shown because OAuth cannot be made real without a registered Google client and redirect credentials.

The score is an evidence-backed concern indicator, not a diagnosis, an exposure measurement, or a prediction of harm. Unknown ingredients are displayed neutrally, and personal profile matches never alter the general score. The curated evidence set is intentionally conservative and should not replace checking packaging or professional medical advice.

Verified chemical-family membership is stored as curated data with a source and confidence. The included PFAS demonstration maps only PTFE using an OECD reference; Ingredia never infers PFAS membership from spelling, and family membership alone does not add score points. Encounter counts mean appearances in analyzed products—not concentration, absorbed dose, toxic load, or biological exposure.
