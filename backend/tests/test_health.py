import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


# ---- health ----------------------------------------------------------------------------


def test_health_is_public_and_reports_the_database(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.data == {"status": "ok", "database": "ok"}


def test_health_returns_503_when_the_database_is_down(api_client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(connection, "cursor", broken)
    response = api_client.get("/api/health/")
    assert response.status_code == 503
    assert response.data["status"] == "error"
