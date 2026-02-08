from fastapi import FastAPI, Request, Response

from token_bucket import TokenBucketRateLimiter, per_min

app = FastAPI()
rate_limiter = TokenBucketRateLimiter(per_min(5, burst=5))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/echo")
async def echo(payload: dict):
    return {"echo": payload}


@app.get("/rate-limited")
def rate_limited(request: Request, response: Response):
    client_host = request.client.host if request.client else "unknown"
    result = rate_limiter.limit(client_host)
    state = result.state

    response.headers["X-RateLimit-Limit"] = str(state.limit)
    response.headers["X-RateLimit-Remaining"] = str(state.remaining)
    response.headers["X-RateLimit-Reset"] = str(state.reset_after)
    if result.limited:
        response.headers["Retry-After"] = str(state.retry_after)
        response.status_code = 429
        return {
            "limited": True,
            "retry_after": state.retry_after,
        }

    return {
        "limited": False,
        "remaining": state.remaining,
    }
