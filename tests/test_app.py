from fastapi.testclient import TestClient

from app.main import app, rate_limiter


client = TestClient(app)


def test_health_check():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_echo():
    payload = {"message": "hello"}
    response = client.post("/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == {"received": payload}


def test_rate_limited():
    rate_limiter._backend._client.clear()
    rate_limiter._backend.expire_info.clear()
    responses = [client.get("/rate-limited", params={"client_id": "tester"}) for _ in range(15)]
    status_codes = [response.status_code for response in responses]
    assert 200 in status_codes
    assert 429 in status_codes
