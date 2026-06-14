import uuid, time, logging, json
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger("d2cflow.requests")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration, 2),
            "ip": request.client.host if request.client else "unknown",
        }))
        return response

_rate_buckets: dict = defaultdict(list)

class RateLimitMiddleware(BaseHTTPMiddleware):
    def _get_limit(self, path: str) -> int:
        if "/api/whatsapp" in path:
            return 100
        return 300

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "0.0.0.0"
        key = f"{ip}:{request.url.path}"
        limit = self._get_limit(request.url.path)
        now = time.time()
        window = 60
        _rate_buckets[key] = [t for t in _rate_buckets[key] if now - t < window]
        if len(_rate_buckets[key]) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded. Try again in a minute."}, status_code=429)
        _rate_buckets[key].append(now)
        return await call_next(request)
