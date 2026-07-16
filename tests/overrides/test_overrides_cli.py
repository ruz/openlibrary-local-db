import json

import sqlite_utils

import overrides
import pipeline


def _build_base_db(db_path):
    db = sqlite_utils.Database(str(db_path))
    db["works"].insert({"ol_id": "OL10W", "title": "Original Title"}, pk="ol_id")
    db.close()


def test_overrides_set_via_cli(tmp_path, capsys):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    _build_base_db(base_path)

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "set", "works", "OL10W", "--field", "title=Fixed Title", "--note", "typo",
    ])

    conn = overrides.get_overrides_db(str(overrides_path))
    row = overrides.get_override(conn, "works", "OL10W")
    assert row is not None
    assert json.loads(row["patch"]) == {"title": "Fixed Title"}
    assert row["note"] == "typo"


def test_overrides_list_and_discard_via_cli(tmp_path, capsys):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    _build_base_db(base_path)

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "set", "works", "OL10W", "--field", "title=Fixed Title",
    ])
    capsys.readouterr()

    pipeline.main(argv=["overrides", "--overrides-db", str(overrides_path), "list"])
    out = capsys.readouterr().out
    assert "works/OL10W" in out

    pipeline.main(argv=["overrides", "--overrides-db", str(overrides_path), "discard", "works", "OL10W"])
    conn = overrides.get_overrides_db(str(overrides_path))
    assert overrides.get_override(conn, "works", "OL10W") is None


def test_overrides_sync_and_resolve_via_cli(tmp_path):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    _build_base_db(base_path)

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "set", "works", "OL10W", "--field", "title=Fixed Title",
    ])

    db = sqlite_utils.Database(str(base_path))
    db["works"].update("OL10W", {"title": "Upstream Changed"})

    pipeline.main(argv=["overrides", "--db", str(base_path), "--overrides-db", str(overrides_path), "sync"])

    conn = overrides.get_overrides_db(str(overrides_path))
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "stale"

    pipeline.main(argv=[
        "overrides", "--overrides-db", str(overrides_path),
        "resolve", "works", "OL10W", "--keep-mine",
    ])
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "active"


def test_overrides_export_and_mark_submitted_via_cli(tmp_path):
    base_path = tmp_path / "base.db"
    overrides_path = tmp_path / "overrides.db"
    export_path = tmp_path / "export.json"
    _build_base_db(base_path)

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "set", "works", "OL10W", "--field", "title=Fixed Title",
    ])

    pipeline.main(argv=[
        "overrides", "--overrides-db", str(overrides_path),
        "export", "--output", str(export_path),
    ])
    data = json.loads(export_path.read_text())
    assert data[0]["ol_key"] == "/works/OL10W"

    pipeline.main(argv=[
        "overrides", "--overrides-db", str(overrides_path),
        "mark-submitted", "works", "OL10W",
    ])
    conn = overrides.get_overrides_db(str(overrides_path))
    assert overrides.get_override(conn, "works", "OL10W")["status"] == "submitted"


def test_overrides_clear_requires_yes(tmp_path):
    overrides_path = tmp_path / "overrides.db"
    base_path = tmp_path / "base.db"
    _build_base_db(base_path)

    pipeline.main(argv=[
        "overrides", "--db", str(base_path), "--overrides-db", str(overrides_path),
        "set", "works", "OL10W", "--field", "title=Fixed Title",
    ])

    try:
        pipeline.main(argv=["overrides", "--overrides-db", str(overrides_path), "clear"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass

    conn = overrides.get_overrides_db(str(overrides_path))
    assert overrides.get_override(conn, "works", "OL10W") is not None

    pipeline.main(argv=["overrides", "--overrides-db", str(overrides_path), "clear", "--yes"])
    assert overrides.list_overrides(conn) == []


def test_run_all_syncs_overrides_when_configured(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"
    overrides_path = tmp_path / "overrides.db"

    def _line(key, data):
        return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])

    (input_dir / "ol_dump_authors_2025-05-01.txt").write_text(
        _line("/authors/OL1A", {"name": "Jane Doe"}) + "\n", encoding="utf-8"
    )
    (input_dir / "ol_dump_works_2025-05-01.txt").write_text(
        _line("/works/OL10W", {"title": "Test Work", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )
    (input_dir / "ol_dump_editions_2025-05-01.txt").write_text(
        _line("/books/OLedX1M", {"title": "Test Edition", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )

    argv = [
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--overrides-db", str(overrides_path),
        "--skip-env",
        "--skip-download",
    ]
    pipeline.main(argv=argv)

    conn = overrides.get_overrides_db(str(overrides_path))
    overrides.set_override(
        conn, "works", "OL10W", {"title": "My Fixed Title"},
        {"ol_id": "OL10W", "title": "Test Work"}, "2025-05-01",
    )

    (input_dir / "ol_dump_works_2025-05-01.txt").write_text(
        _line("/works/OL10W", {"title": "Upstream Renamed", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )
    pipeline.main(argv=argv)

    assert overrides.get_override(conn, "works", "OL10W")["status"] == "stale"


def test_run_all_is_noop_for_overrides_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("OVERRIDES_DB", raising=False)
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"

    def _line(key, data):
        return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])

    (input_dir / "ol_dump_authors_2025-05-01.txt").write_text(
        _line("/authors/OL1A", {"name": "Jane Doe"}) + "\n", encoding="utf-8"
    )
    (input_dir / "ol_dump_works_2025-05-01.txt").write_text(
        _line("/works/OL10W", {"title": "Test Work", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )
    (input_dir / "ol_dump_editions_2025-05-01.txt").write_text(
        _line("/books/OLedX1M", {"title": "Test Edition", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )

    argv = [
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
        "--skip-download",
    ]
    pipeline.main(argv=argv)  # should not raise even though overrides are unset
