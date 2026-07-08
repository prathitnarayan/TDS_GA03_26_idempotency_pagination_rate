from collections import defaultdict, deque
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import uuid
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
def create_order(
    order: OrderRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")

    if idempotency_key in IDEMPOTENCY_STORE:
        return IDEMPOTENCY_STORE[idempotency_key]

    created = {
        "id": str(uuid.uuid4()),
        "item": order.item,
        "amount": order.amount,
    }

    IDEMPOTENCY_STORE[idempotency_key] = created
    return created


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