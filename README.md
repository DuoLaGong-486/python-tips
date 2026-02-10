# python-tips
FastAPI demo with token bucket rate limiter and load testing helpers.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the app
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Run tests
```bash
pytest
```

## Load test (brute force)
```bash
python scripts/load_test.py --base-url http://127.0.0.1:8000 --concurrency 100 --requests 1000 --payload-size 256
```
