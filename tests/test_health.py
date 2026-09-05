import app


def test_health(client):
    antwort = client.get("/health")
    assert antwort.status_code == 200
    assert antwort.json() == {"status": "ok", "version": app.__version__}
