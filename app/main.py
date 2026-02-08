from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from token_bucket import per_sec, TokenBucketRateLimiter


app = FastAPI()
rate_limiter = TokenBucketRateLimiter(per_sec(5, burst=10))


@app.get("/healthz")
def health_check():
    return {"status": "ok"}


@app.post("/echo")
async def echo(request: Request):
    payload = await request.json()
    return {"received": payload}


@app.get("/rate-limited")
def rate_limited(client_id: str = "anonymous"):
    result = rate_limiter.limit(client_id)
    state = result.state
    headers = {
        "X-RateLimit-Limit": str(state.limit),
        "X-RateLimit-Remaining": str(state.remaining),
        "X-RateLimit-Reset": str(state.reset_after),
        "X-RateLimit-RetryAfter": str(state.retry_after),
    }
    if result.limited:
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limited"},
            headers=headers,
        )
    return JSONResponse(content={"detail": "ok"}, headers=headers)
