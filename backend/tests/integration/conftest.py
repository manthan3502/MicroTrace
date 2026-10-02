import os
import uuid

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def db_engine():
    """Use a disposable schema, leaving all existing public telemetry untouched."""
    url = os.environ.get("MICROTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MICROTRACE_TEST_DATABASE_URL to a migrated PostgreSQL database")
    schema = "microtrace_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'CREATE TABLE "{schema}".spans (LIKE public.spans INCLUDING ALL)'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def collector_app(db_engine):
    from services.trace_backend.database import get_engine
    from services.trace_backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_engine] = lambda: db_engine
    return app


@pytest.fixture
def collector(collector_app):
    from fastapi.testclient import TestClient

    with TestClient(collector_app) as client:
        yield client
