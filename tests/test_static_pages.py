import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    import app.core.db as _db
    from app.core.config import load_config
    from app.core import provision
    c = _db.connect(db_path); _db.init_schema(c)
    provision.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()
    from app.main import create_app
    return TestClient(create_app())


def test_dashboard_is_phone_layout(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "dash--phone" in r.text
    assert 'id="tiles-grid"' in r.text
    # old two-grid markup must be gone
    assert 'id="summary-grid"' not in r.text
    assert 'id="charts-grid"' not in r.text
