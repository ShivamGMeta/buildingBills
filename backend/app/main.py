from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, billing_api, tenant_api, units, users

app = FastAPI(title="Building Bills API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def create_schema():
    # Dev convenience; production uses Alembic migrations.
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(units.router)
app.include_router(billing_api.router)
app.include_router(tenant_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
