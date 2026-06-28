"""
Tests that BASE_PATH env var correctly scopes all routes under the prefix
(or leaves them at / when unset).  Self-contained — does not share fixtures
with other test files.
"""
import pytest
from starlette.testclient import TestClient


def _make_client(tmp_path, monkeypatch, base):
    """Provision a fresh temp DB, set BASE_PATH, return a TestClient."""
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    if base:
        monkeypatch.setenv("BASE_PATH", base)
    else:
        monkeypatch.delenv("BASE_PATH", raising=False)

    import app.core.db as _db
    from app.core.config import load_config
    from app.core import provision

    c = _db.connect(db_path)
    _db.init_schema(c)
    provision.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()

    from app.main import create_app
    return TestClient(create_app(), follow_redirects=False)


def test_prefixed_api_dashboard(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, "/paper-market")
    assert client.get("/paper-market/api/dashboard").status_code == 200


def test_prefixed_api_dashboard_not_at_root(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, "/paper-market")
    assert client.get("/api/dashboard").status_code == 404


def test_prefixed_root_redirect(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, "/paper-market")
    r = client.get("/paper-market/")
    assert r.status_code in (307, 308)
    assert r.headers["location"].endswith("/paper-market/dashboard.html")


def test_unprefixed_api_dashboard(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, "")
    assert client.get("/api/dashboard").status_code == 200


def test_unprefixed_no_paper_market_route(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, "")
    assert client.get("/paper-market/api/dashboard").status_code == 404
