import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from services.notification.main import app as notification_app
from services.order.main import app as order_app
from services.payment.main import app as payment_app
from services.trace_backend import main as trace_backend


@pytest.mark.parametrize("app", [order_app, payment_app, notification_app])
def test_demo_health(app):
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trace_health_checks_database(monkeypatch):
    checks = []
    monkeypatch.setattr(trace_backend, "check_database", lambda: checks.append(True))
    with TestClient(trace_backend.app) as client:
        response = client.get("/health")
    assert checks == [True]
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trace_health_reports_database_failure_without_details(monkeypatch):
    def unavailable():
        raise OperationalError("private connection details", {}, Exception("private details"))

    monkeypatch.setattr(trace_backend, "check_database", unavailable)
    with TestClient(trace_backend.app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
