# Ingredient Intelligence Platform

Backend-first prototype for transparent ingredient-list analysis. It parses labels, resolves aliases, returns source-linked evidence, creates a deterministic evidence-concern score, and keeps personal avoid-list alerts separate from that general score.

The included frontend is configured to run locally at `http://localhost:3000` and connect to this API.

## Frontend

The React frontend lives in `frontend/`. It provides a connected paste-and-analyze workspace, evidence detail drawer, preference action, comparison view, and ingredient explorer.

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
- `PUT /api/v1/users/{user_id}/preferences`
- `POST /api/v1/comparisons`

The score is an evidence-backed concern indicator, not a diagnosis, an exposure measurement, or a prediction of harm. Seed evidence is demo data and must be replaced by reviewed, source-attributed production data before any real-world use.
