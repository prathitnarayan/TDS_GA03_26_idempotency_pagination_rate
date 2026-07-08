from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import base64
import time
import uuid

app = FastAPI()

# ---------------- CORS ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# ---------------- Constants ----------------

TOTAL_ORDERS = 54
RATE_LIMIT = 19
WINDOW_SECONDS = 10

# ---------------- Fixed Order Catalog ----------------

ORDERS = [
    {
        "id": i,
        "item": f"Item {i}",
        "amount": float(i * 10),
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# ---------------- In-memory Stores ----------------

idempotency_store = {}

client_requests = defaultdict(deque)

# ---------------- Rate Limiter ----------------


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")

    if client_id:
        now = time.time()
        bucket = client_requests[client_id]

        while bucket and bucket[0] <= now - WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = max(1, int(WINDOW_SECONDS - (now - bucket[0])))

            response = JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
            )

            response.headers["Retry-After"] = str(retry_after)
            return response

        bucket.append(now)

    return await call_next(request)

# ---------------- Idempotent POST ----------------


@app.post("/orders")
async def create_order(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key",
        )

    # Existing request
    if idempotency_key in idempotency_store:
        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key],
        )

    body = {}

    try:
        if request.headers.get("content-length"):
            body = await request.json()
    except Exception:
        body = {}

    order = {
        "id": str(uuid.uuid4()),
        **body,
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
    )

# ---------------- Cursor Pagination ----------------


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str | None = None,
):
    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid cursor",
            )

    limit = max(1, min(limit, TOTAL_ORDERS))

    items = ORDERS[start:start + limit]

    next_cursor = None

    if start + limit < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(start + limit).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }

# ---------------- Root ----------------


@app.get("/")
def root():
    return {
        "status": "running"
    }