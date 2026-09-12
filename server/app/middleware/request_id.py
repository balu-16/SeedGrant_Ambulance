import re
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# inbound X-Request-ID must be 1-64 chars of [-0-9a-zA-Z]; anything else is
# replaced with a fresh id (prevents header-injection/log-forgery abuse)
_REQUEST_ID_RE = re.compile(r"[-0-9a-zA-Z]{1,64}")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", "")
        if not _REQUEST_ID_RE.fullmatch(rid):
            rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        return resp
