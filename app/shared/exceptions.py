from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code


def error_payload(message: str, errors: list[str]) -> dict[str, Any]:
    return {
        "success": False,
        "message": message,
        "data": None,
        "errors": errors,
        "meta": {
            "request_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.message, [exc.code]),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "Validation failed.",
                [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()],
            ),
        )
