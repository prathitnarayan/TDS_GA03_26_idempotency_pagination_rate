import time
import uuid
from threading import Lock

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Assigned values
# ---------------------------------------------------------------------------
TOTAL_ORDERS = 54
RATE_LIMIT_COUNT = 19
RATE_LIMIT_WINDOW_SECONDS = 10

# ---------------------------------------------------------------------------
# Fixed catalog of orders 1..T, used only for GET pagination
# ---------------------------------------------------------------------------
CATALOG = [
    {"id": i, "item": f"item-{i}", "status": "catalog"}
    for i in range(1, TOTAL_ORDERS + 1)
]

# ---------------------------------------------------------------------------
# Idempotency store for POST /orders (separate id space from the catalog)
# ---------------------------------------------------------------------------
_idempotency_lock = Lock()
idempotency_store: dict[str, dict] = {}
_next_created_id = TOTAL_ORDERS + 1

# ---------------------------------------------------------------------------
# Per-client rate limiter (sliding window)
# ---------------------------------------------------------------------------
_rate_lock = Lock()
client_hits: dict[str, list[float]] = {}


def check_rate_limit(client_id: str):
    now = time.time()
    with _rate_lock:
        hits = client_hits.setdefault(client_id, [])
        # prune entries outside the window
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        hits[:] = [t for t in hits if t > cutoff]

        if len(hits) >= RATE_LIMIT_COUNT:
            oldest = hits[0]
            retry_after = max(1, int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)


@app.post("/orders")
async def create_order(request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                        x_client_id: str | None = Header(default=None, alias="X-Client-Id")):
    if x_client_id:
        check_rate_limit(x_client_id)

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    with _idempotency_lock:
        if idempotency_key in idempotency_store:
            existing = idempotency_store[idempotency_key]
            return JSONResponse(status_code=200, content=existing)

        global _next_created_id
        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}

        order = {
            "id": str(_next_created_id),
            "status": "created",
            **{k: v for k, v in body.items() if k != "id"},
        }
        _next_created_id += 1
        idempotency_store[idempotency_key] = order

    return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: str | None = None,
                       x_client_id: str | None = Header(default=None, alias="X-Client-Id")):
    if x_client_id:
        check_rate_limit(x_client_id)

    if limit <= 0:
        limit = 10

    start = 0
    if cursor:
        try:
            start = int(cursor)
        except ValueError:
            start = 0

    start = max(0, start)
    page = CATALOG[start:start + limit]
    end = start + len(page)

    next_cursor = str(end) if end < TOTAL_ORDERS else None

    return {
        "items": page,
        "orders": page,
        "next_cursor": next_cursor,
        "next": next_cursor,
    }