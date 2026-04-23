from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.bootstrap import bootstrap_database
from app.db.health import check_database
from app.shared.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="PikuAI Backend", version="0.1.0")

    configured_origins = [
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ]
    allowed_origins = [
        settings.admin_origin,
        "http://localhost:19006",
        "http://127.0.0.1:19006",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:8082",
        "http://127.0.0.1:8082",
        *configured_origins,
    ]
    dev_origin_regex = (
        r"^https?://("
        r"localhost|127\.0\.0\.1|0\.0\.0\.0|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
        if settings.node_env == "development"
        else None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=dev_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    def startup() -> None:
        bootstrap_database()

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {"ok": True, "service": "pikuai-backend"}

    @app.get("/health/db")
    def database_health() -> dict[str, object]:
        database = check_database()
        return {
            "ok": database["connected"],
            "service": "pikuai-backend",
            "database": database,
        }

    return app


app = create_app()
