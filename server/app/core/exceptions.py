from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger("errors")


class AppError(Exception):
    status_code: int = 400
    code: str = "APP_ERROR"

    def __init__(self, message: str, *, code: str = "", status_code: int = 0):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    rid = getattr(request.state, "request_id", "-")
    log.warning(
        "app_error", code=exc.code, message=exc.message, request_id=rid, path=request.url.path
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.message},
            "request_id": rid,
        },
    )


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", "-")
    log.error("unhandled", error=str(exc), request_id=rid, path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": "INTERNAL", "message": "Internal server error"},
            "request_id": rid,
        },
    )
