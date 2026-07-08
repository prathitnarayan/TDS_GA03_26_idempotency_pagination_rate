from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "ak_0oo7oz5ubfhwnono3d4uxn7i"

# ---------------------------------------------------------------------------
# EDIT THIS before deploying — put your logged-in email address here.
# ---------------------------------------------------------------------------
EMAIL = "25ds2000019@ds.study.iitm.ac.in"


@app.post("/analytics")
async def analytics(request: Request, x_api_key: str | None = Header(default=None)):
    if x_api_key != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    body = await request.json()
    events = body.get("events", [])

    total_events = len(events)
    unique_users = set()
    revenue = 0.0
    per_user_positive = defaultdict(float)

    for event in events:
        user = event.get("user")
        amount = event.get("amount", 0)

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0

        if user is not None:
            unique_users.add(user)

        if amount > 0:
            revenue += amount
            if user is not None:
                per_user_positive[user] += amount

    top_user = None
    if per_user_positive:
        top_user = max(per_user_positive.items(), key=lambda kv: kv[1])[0]

    return {
        "email": EMAIL,
        "total_events": total_events,
        "unique_users": len(unique_users),
        "revenue": revenue,
        "top_user": top_user,
    }