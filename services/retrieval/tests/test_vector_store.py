import pytest
from app import vector_store as vs


class FakeCursor:
    def __init__(self):
        self.executed = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, rows):
        self.executed.append((sql, rows))

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def _fake_get_conn(conn, monkeypatch):
    monkeypatch.setattr(vs, "get_conn", lambda: conn)
    return conn


def test_ensure_schema_executes_ddl(monkeypatch):
    conn = FakeConn()
    _fake_get_conn(conn, monkeypatch)
    vs.ensure_schema()
    assert len(conn.cursor_obj.executed) == len(vs.SCHEMA_DDL)
    assert conn.committed is True


def test_upsert_chunks_replaces_rows(monkeypatch):
    conn = FakeConn()
    _fake_get_conn(conn, monkeypatch)
    rows = [("a.py", "content", [0.1, 0.2]), ("b.py", "more", [0.3, 0.4])]
    assert vs.upsert_chunks("repo", rows) == 2
    sqls = [sql for sql, _ in conn.cursor_obj.executed]
    assert "DELETE FROM code_chunks" in sqls[0]
    assert "INSERT INTO code_chunks" in sqls[1]
    assert conn.committed is True


def test_similarity_search_returns_rows(monkeypatch):
    conn = FakeConn()
    conn.cursor_obj.rows = [("a.py", "content", 0.95)]
    _fake_get_conn(conn, monkeypatch)
    rows = vs.similarity_search("repo", [0.1, 0.2], 5)
    assert rows == [("a.py", "content", 0.95)]
    sql = conn.cursor_obj.executed[0][0]
    assert "<=>" in sql
    assert "LIMIT %s" in sql


def test_get_conn_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        vs.get_conn()
