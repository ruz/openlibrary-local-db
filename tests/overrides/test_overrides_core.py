import json

import overrides


def test_get_overrides_db_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("OVERRIDES_DB", raising=False)
    assert overrides.get_overrides_db() is None


def test_get_overrides_db_creates_schema(tmp_path):
    db_path = tmp_path / "overrides.db"
    conn = overrides.get_overrides_db(str(db_path))
    assert conn is not None
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'overrides'").fetchone()


def test_set_and_get_override(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title", "description": "Original desc"}
    result = overrides.set_override(
        conn, "works", "OL10W", {"title": "Fixed Title"}, base_row, "2026-06-30", note="typo fix"
    )
    assert result["status"] == "active"
    assert json.loads(result["patch"]) == {"title": "Fixed Title"}
    assert json.loads(result["base_snapshot"]) == {"title": "Original Title"}
    assert result["note"] == "typo fix"

    fetched = overrides.get_override(conn, "works", "OL10W")
    assert fetched["ol_id"] == "OL10W"


def test_set_override_upserts_existing_row(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "First Fix"}, base_row, "2026-06-30")
    overrides.set_override(conn, "works", "OL10W", {"title": "Second Fix"}, base_row, "2026-07-01")

    rows = overrides.list_overrides(conn)
    assert len(rows) == 1
    assert json.loads(rows[0]["patch"]) == {"title": "Second Fix"}


def test_discard_override(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")

    assert overrides.discard_override(conn, "works", "OL10W") is True
    assert overrides.get_override(conn, "works", "OL10W") is None
    assert overrides.discard_override(conn, "works", "OL10W") is False


def test_list_overrides_filters_by_status_and_entity_type(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(conn, "works", "OL10W", {"title": "A"}, {"ol_id": "OL10W", "title": "x"}, "2026-06-30")
    overrides.set_override(conn, "authors", "OL1A", {"name": "B"}, {"ol_id": "OL1A", "name": "y"}, "2026-06-30")
    overrides.mark_submitted(conn, "authors", "OL1A")

    assert len(overrides.list_overrides(conn, entity_type="works")) == 1
    assert len(overrides.list_overrides(conn, status="submitted")) == 1
    assert len(overrides.list_overrides(conn)) == 2


def test_mark_submitted(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")

    assert overrides.mark_submitted(conn, "works", "OL10W") is True
    row = overrides.get_override(conn, "works", "OL10W")
    assert row["status"] == "submitted"
    assert row["submitted_at"] is not None
    assert overrides.mark_submitted(conn, "works", "OL99W") is False


def test_clear_overrides(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")

    overrides.clear_overrides(conn)
    assert overrides.list_overrides(conn) == []


def test_resolve_keep_mine_clears_stale_flag(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")
    conn.execute("UPDATE overrides SET status = 'stale' WHERE entity_type = 'works' AND ol_id = 'OL10W'")
    conn.commit()

    assert overrides.resolve_override(conn, "works", "OL10W", "keep-mine") is True
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "active"


def test_resolve_accept_upstream_and_discard_both_remove_row(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")

    assert overrides.resolve_override(conn, "works", "OL10W", "accept-upstream") is True
    assert overrides.get_override(conn, "works", "OL10W") is None


def test_export_overrides_writes_ol_keys(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(
        conn, "editions", "OLedX1M", {"title": "Fixed Edition"},
        {"ol_id": "OLedX1M", "title": "Original"}, "2026-06-30", note="typo",
    )
    output_path = tmp_path / "export.json"

    count = overrides.export_overrides(conn, str(output_path), status="active")
    assert count == 1

    data = json.loads(output_path.read_text())
    assert data[0]["entity_type"] == "editions"
    assert data[0]["ol_key"] == "/books/OLedX1M"
    assert data[0]["patch"] == {"title": "Fixed Edition"}


def test_export_overrides_excludes_non_matching_status(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Fixed"}, base_row, "2026-06-30")
    overrides.mark_submitted(conn, "works", "OL10W")

    output_path = tmp_path / "export.json"
    count = overrides.export_overrides(conn, str(output_path), status="active")
    assert count == 0
