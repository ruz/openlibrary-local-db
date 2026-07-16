import json

import sqlite_utils

import overrides
import pipeline


def _build_base_db(db_path):
    db = sqlite_utils.Database(str(db_path))
    db["works"].insert({"ol_id": "OL10W", "title": "Original Title"}, pk="ol_id")
    db.close()


def test_suggestions_list_via_cli(tmp_path, capsys):
    overrides_path = tmp_path / "overrides.db"
    conn = overrides.get_overrides_db(str(overrides_path))
    overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "Fixed"}, None, "hash1")
    capsys.readouterr()

    pipeline.main(argv=["overrides", "--overrides-db", str(overrides_path), "suggestions", "list"])
    out = capsys.readouterr().out
    assert "works/OL10W" in out
    assert "pending" in out


def test_suggestions_approve_patch_via_cli(tmp_path):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(overrides_path))
    suggestion = overrides.create_suggestion(
        conn, "works", "OL10W", "patch", {"title": "Fixed Title"}, "typo", "hash1"
    )

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path), "--date", "2025-01-01",
        "suggestions", "approve", str(suggestion["id"]),
    ])

    override = overrides.get_override(conn, "works", "OL10W")
    assert json.loads(override["patch"]) == {"title": "Fixed Title"}
    assert overrides.get_suggestion(conn, suggestion["id"])["status"] == "approved"


def test_suggestions_approve_delete_via_cli(tmp_path):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    _build_base_db(base_path)

    conn = overrides.get_overrides_db(str(overrides_path))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "Was Fixed"}, {"ol_id": "OL10W", "title": "Original Title"}, "2025-01-01"
    )
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "delete", {}, None, "hash1")

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "suggestions", "approve", str(suggestion["id"]),
    ])

    assert overrides.get_override(conn, "works", "OL10W") is None


def test_suggestions_reject_via_cli(tmp_path):
    overrides_path = tmp_path / "overrides.db"
    conn = overrides.get_overrides_db(str(overrides_path))
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "x"}, None, "hash1")

    pipeline.main(argv=[
        "overrides", "--overrides-db", str(overrides_path),
        "suggestions", "reject", str(suggestion["id"]),
    ])

    assert overrides.get_suggestion(conn, suggestion["id"])["status"] == "rejected"
    assert overrides.get_override(conn, "works", "OL10W") is None


def test_suggestions_approve_missing_record_exits(tmp_path):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    sqlite_utils.Database(str(base_path))["works"].insert({"ol_id": "OTHER", "title": "x"}, pk="ol_id")

    conn = overrides.get_overrides_db(str(overrides_path))
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "Fixed"}, None, "hash1")

    try:
        pipeline.main(argv=[
            "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
            "suggestions", "approve", str(suggestion["id"]),
        ])
        assert False, "expected SystemExit"
    except SystemExit:
        pass
