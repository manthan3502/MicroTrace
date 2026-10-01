import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})


def check_database() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
