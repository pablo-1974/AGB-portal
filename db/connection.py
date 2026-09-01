import os
import queue
import threading
import time
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def _database_url() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL no está definida en el entorno")
    return url


def _make_conn():
    return psycopg.connect(_database_url(), row_factory=dict_row)


def _conn_alive(conn, *, max_idle_sec: float = 45.0) -> bool:
    """Neon/pooler cierra SSL en idle; no reutilizar conexiones muertas."""
    if conn is None or getattr(conn, "closed", True):
        return False
    last = getattr(conn, "_pool_returned_at", None)
    if last is not None and (time.monotonic() - float(last)) < max_idle_sec:
        return True
    try:
        conn.execute("SELECT 1")
        conn.rollback()
        return True
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return False


class _SimplePool:
    """Pool ligero sin dependencia extra (reutiliza conexiones TCP)."""

    def __init__(self, max_size: int = 10):
        self._max = max(2, int(max_size))
        self._q: queue.LifoQueue = queue.LifoQueue(maxsize=self._max)
        self._created = 0
        self._lock = threading.Lock()

    def _discard(self, conn) -> None:
        if conn is None:
            return
        try:
            if not getattr(conn, "closed", True):
                conn.close()
        except Exception:
            pass
        with self._lock:
            self._created = max(0, self._created - 1)

    def getconn(self):
        # Probar varias del pool: Neon puede haber cerrado las idle.
        for _ in range(self._max + 1):
            try:
                conn = self._q.get_nowait()
            except queue.Empty:
                break
            if _conn_alive(conn):
                return conn
            self._discard(conn)

        with self._lock:
            if self._created < self._max:
                self._created += 1
                create = True
            else:
                create = False
        if create:
            try:
                return _make_conn()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise

        conn = self._q.get(timeout=5)
        if _conn_alive(conn):
            return conn
        self._discard(conn)
        with self._lock:
            self._created += 1
        try:
            return _make_conn()
        except Exception:
            with self._lock:
                self._created = max(0, self._created - 1)
            raise

    def putconn(self, conn, *, discard: bool = False) -> None:
        if conn is None:
            return
        if discard or getattr(conn, "closed", False):
            self._discard(conn)
            return
        try:
            conn._pool_returned_at = time.monotonic()
            self._q.put_nowait(conn)
        except queue.Full:
            self._discard(conn)


_pool: _SimplePool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> _SimplePool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            raw = (os.getenv("DB_POOL_SIZE") or "10").strip()
            try:
                size = int(raw)
            except ValueError:
                size = 10
            _pool = _SimplePool(max_size=size)
        return _pool


def _is_conn_error(exc: BaseException) -> bool:
    if isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)):
        return True
    msg = str(exc).lower()
    return "ssl connection has been closed" in msg


@contextmanager
def get_db():
    pool = _get_pool()
    conn = pool.getconn()
    discard = False
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        discard = _is_conn_error(exc)
        try:
            conn.rollback()
        except Exception:
            discard = True
        raise
    finally:
        pool.putconn(conn, discard=discard)
