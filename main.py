from collections import defaultdict, deque
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import uuid
import base64
from fastapi import Request

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

TOTAL_ORDERS = 54
RATE_LIMIT = 19
WINDOW = 10  # seconds

# Fixed catalog
ORDERS = [
    {
        "id": i,
        "item": f"Item {i}",
        "amount": float(i * 10),
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# Idempotency store
IDEMPOTENCY_STORE = {}

# Rate limiting
CLIENT_REQUESTS = defaultdict(deque)


class OrderRequest(BaseModel):
    item: str
    amount: float


@app.post("/orders", status_code=201)
async def create_order(
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key")

    if idempotency_key in IDEMPOTENCY_STORE:
        return IDEMPOTENCY_STORE[idempotency_key]

    try:
        body = await request.json()
    except Exception:
        body = {}

    order = {
        "id": str(uuid.uuid4()),
        **body,
    }

    IDEMPOTENCY_STORE[idempotency_key] = order
    return order


@app.get("/orders")
def list_orders(limit: int = 10, cursor: str | None = None):
    start = 0

    if cursor:
        start = int(base64.b64decode(cursor).decode())

    items = ORDERS[start:start + limit]

    next_cursor = None
    if start + limit < len(ORDERS):
        next_cursor = base64.b64encode(
            str(start + limit).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.middleware("http")
async def rate_limit(request, call_next):
    client = request.headers.get("X-Client-Id")

    if client:
        now = time.time()
        bucket = CLIENT_REQUESTS[client]

        while bucket and bucket[0] <= now - WINDOW:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = int(WINDOW - (now - bucket[0])) + 1

            response = Response(
                status_code=429,
                content="Too Many Requests",
            )

            response.headers["Retry-After"] = str(retry_after)
            return response

        bucket.append(now)

    return await call_next(request)