import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def _database_url() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL no está definida en el entorno")
    return url


@contextmanager
def get_db():
    conn = psycopg.connect(_database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
