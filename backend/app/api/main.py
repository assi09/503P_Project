"""The HTTP API the mobile app talks to.

Run from the repository root: `uvicorn app.api.main:app --app-dir backend --reload`.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api import auth, chat, data, reports
from app.api.errors import ApiError
from app.api.schemas import ErrorBody, ErrorResponse
from app.auth.accounts import AuthError
from app.config import settings
from app.ingest.takeout import IngestError

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(by_alias=True))


def create_app() -> FastAPI:
    app = FastAPI(title="Fitbit agent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Every error has the same shape: {"error": {"code": ..., "message": ...}}.
    @app.exception_handler(IngestError)
    async def ingest_error(_: Request, exc: IngestError) -> JSONResponse:
        logger.warning("Data unavailable: %s", exc)
        return _error(503, "data_unavailable", "Your Fitbit data could not be loaded.")

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(AuthError)
    async def auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request", "The request is not valid.")

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(data.router)
    app.include_router(reports.router)
    return app


app = create_app()
