import sqlite_utils

import overrides


def _build_base_db(db_path, title="Original Title"):
    db = sqlite_utils.Database(str(db_path))
    db["works"].insert({"ol_id": "OL10W", "title": title}, pk="ol_id")
    db.close()


def test_sync_leaves_active_when_base_unchanged(tmp_path):
    base_path = tmp_path / "base.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "My Fixed Title"},
        {"ol_id": "OL10W", "title": "Original Title"}, "2026-06-30",
    )

    result = overrides.sync_overrides(conn, str(base_path))
    assert result == {"stale": 0, "orphaned": 0}
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "active"


def test_sync_flags_stale_on_upstream_drift(tmp_path):
    base_path = tmp_path / "base.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "My Fixed Title"},
        {"ol_id": "OL10W", "title": "Original Title"}, "2026-06-30",
    )

    db = sqlite_utils.Database(str(base_path))
    db["works"].update("OL10W", {"title": "Upstream Changed Title"})

    result = overrides.sync_overrides(conn, str(base_path))
    assert result == {"stale": 1, "orphaned": 0}
    row = overrides.get_override(conn, "works", "OL10W")
    assert row["status"] == "stale"
    # base_snapshot stays frozen at the value captured when the override was made
    assert "Original Title" in row["base_snapshot"]


def test_sync_flags_orphaned_when_base_record_gone(tmp_path):
    base_path = tmp_path / "base.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "My Fixed Title"},
        {"ol_id": "OL10W", "title": "Original Title"}, "2026-06-30",
    )

    db = sqlite_utils.Database(str(base_path))
    db["works"].delete("OL10W")

    result = overrides.sync_overrides(conn, str(base_path))
    assert result == {"stale": 0, "orphaned": 1}
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "orphaned"


def test_sync_only_examines_active_overrides(tmp_path):
    base_path = tmp_path / "base.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "My Fixed Title"},
        {"ol_id": "OL10W", "title": "Original Title"}, "2026-06-30",
    )
    overrides.mark_submitted(conn, "works", "OL10W")

    db = sqlite_utils.Database(str(base_path))
    db["works"].update("OL10W", {"title": "Upstream Changed Title"})

    result = overrides.sync_overrides(conn, str(base_path))
    assert result == {"stale": 0, "orphaned": 0}
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "submitted"
