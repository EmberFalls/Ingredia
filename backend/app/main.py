from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware
from app.db.database import Base, SessionLocal, engine
from app.db.migrations import apply_local_schema_migrations
from app.db.seed import seed_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_local_schema_migrations(engine)
    with SessionLocal() as session:
        seed_database(session)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware, requests_per_minute=settings.rate_limit_requests_per_minute)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Catalog-Result", "X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)
app.include_router(router, prefix="/api/v1")
