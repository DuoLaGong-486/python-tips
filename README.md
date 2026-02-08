# python-tips

just some trash

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /healthz`: health check.
- `POST /echo`: echoes JSON payload.
- `GET /rate-limited`: token-bucket limited endpoint with `X-RateLimit-*` headers.
