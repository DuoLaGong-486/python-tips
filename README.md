# python-tips
just some trash

## Load testing

Configuration lives in `tests/load/config.py` and can be overridden with environment variables:

- `LOAD_USERS` (concurrency)
- `LOAD_DURATION` (seconds)
- `LOAD_PAYLOAD_SIZE` (bytes)
- `LOAD_URL` (target URL)

Run the load test script with:

```bash
python -m tests.load.run_load
```

### Recommended baseline

- 100 concurrent users
- 60 seconds duration
- P95 latency < 200 ms
- Error rate < 1%
