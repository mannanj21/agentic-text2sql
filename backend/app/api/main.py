import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.config import get_settings
from app.logging import request_id_ctx, setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory for the FastAPI backend."""

    # Configure logging before doing anything else
    setup_logging()

    settings = get_settings()
    if settings.ALLOW_PRIVATE_HOSTS:
        logger.warning(
            "allow_private_hosts_enabled",
            extra={"security_warning": "SSRF private-address protection is disabled"},
        )

    app = FastAPI(
        title="Agentic Text-to-SQL Analytics Platform",
        version="0.1.0",
        description="Translates natural language questions into SQL queries safely.",
    )

    # Register middlewares
    @app.middleware("http")
    async def trace_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Assigns a request_id to every incoming request and stores it in contextvar."""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Routes
    app.include_router(auth_router)

    @app.get("/health", tags=["System"])
    async def health_check() -> JSONResponse:
        """Basic health check endpoint.

        Note: Future iterations will check DB connectivity here.
        """
        return JSONResponse(content={"status": "ok", "environment": settings.APP_ENV})

    return app


# The ASGI application instance
app = create_app()
