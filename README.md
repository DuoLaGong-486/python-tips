# python-tips
just some trash

## Load testing

Run the async HTTPX load script (requires `pip install httpx`):

```bash
python tests/load/httpx_stress.py --host http://127.0.0.1:8000 --concurrency 100 --duration 15 --payload-size 2048 --csv load_results.csv
```
