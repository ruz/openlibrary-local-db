import sqlite3


class _RaisingCursor:
    def execute(self, *args, **kwargs):
        raise sqlite3.OperationalError("boom")


class _RaisingConnection:
    def cursor(self):
        return _RaisingCursor()


def test_operational_error_returns_400_json(flask_app, client, monkeypatch):
    monkeypatch.setattr(flask_app, "con", _RaisingConnection())
    resp = client.get("/v1/edition/OLedA1")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "boom"}
