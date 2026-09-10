# Ingredient Intelligence Platform

Local-first prototype for transparent ingredient-list analysis. It parses pasted or OCR-extracted labels, resolves aliases, returns source-linked evidence, creates a deterministic evidence-concern score, and keeps personal alerts separate from that general score.

The included frontend is configured to run locally at `http://localhost:3000` and connect to this API.

## Frontend

The React frontend lives in `frontend/`. It provides label OCR, catalog and barcode search, evidence detail, saved profiles and history, product comparison, and catalog-data reporting.

```powershell
cd frontend
pnpm dev
```

The frontend expects the API at `http://127.0.0.1:8000/api/v1` by default. Set `NEXT_PUBLIC_API_BASE_URL` to point at another API instance.

## Run locally

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation. The application creates and seeds a local SQLite database on startup.

## Test

```powershell
cd backend
python -m pytest
```

## Implemented API

- `GET /api/v1/health`
- `POST /api/v1/analyses/text`
- `GET /api/v1/ingredients?query=...`
- `GET /api/v1/ingredients/{ingredient_id}`
- `GET /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `POST /api/v1/products/{product_id}/analyze`
- `POST /api/v1/products/{product_id}/reports`
- `PUT /api/v1/users/{user_id}/preferences`
- `GET /api/v1/users/{user_id}/preferences`
- `GET|PUT /api/v1/users/{user_id}/profile`
- `GET /api/v1/users/{user_id}/history`
- `POST /api/v1/comparisons`

API responses include request IDs, conservative security headers, and a configurable local rate limit. Catalog imports reconcile matching barcodes across providers, and catalog records retain source and retrieval metadata.

## Production boundary

The current `local-demo` user and SQLite database are development-only. Before public deployment, connect a real identity provider, enforce ownership from verified server-side identity, use a shared production database with versioned migrations, and replace the in-memory rate limiter with a distributed service. Do not place OAuth secrets or database credentials in the frontend or commit them to Git.

The score is an evidence-backed concern indicator, not a diagnosis, an exposure measurement, or a prediction of harm. Source-linked seed records are intentionally conservative and require ongoing domain review before real-world reliance.
