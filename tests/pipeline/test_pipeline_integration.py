import json

import sqlite_utils

import pipeline


def _line(key, data):
    return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])


def _write_fixture_dumps(input_dir, date_str="2025-05-01"):
    (input_dir / f"ol_dump_authors_{date_str}.txt").write_text(
        _line("/authors/OL1A", {"name": "Jane Doe"}) + "\n", encoding="utf-8"
    )
    (input_dir / f"ol_dump_works_{date_str}.txt").write_text(
        _line("/works/OL10W", {"title": "Test Work", "authors": [{"key": "/authors/OL1A"}]}) + "\n",
        encoding="utf-8",
    )
    (input_dir / f"ol_dump_editions_{date_str}.txt").write_text(
        _line("/books/OLedX1M", {
            "title": "Test Edition",
            "isbn_10": ["0-261-10221-4"],
            "isbn_13": ["978-0-261-10221-4"],
            "authors": [{"key": "/authors/OL1A"}],
        }) + "\n",
        encoding="utf-8",
    )


def _make_dirs(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    return input_dir, output_dir


def test_all_builds_full_database(tmp_path):
    input_dir, output_dir = _make_dirs(tmp_path)
    _write_fixture_dumps(input_dir)
    db_path = tmp_path / "test.db"

    pipeline.main(argv=[
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
    ])

    db = sqlite_utils.Database(str(db_path))
    assert db["authors"].count == 1
    assert db["works"].count == 1
    assert db["editions"].count == 1

    isbn_rows = list(db["isbn_lookup"].rows)
    assert {"isbn": "0261102214", "ol_id": "OLedX1M"} in isbn_rows
    assert {"isbn": "9780261102214", "ol_id": "OLedX1M"} in isbn_rows

    assert db["editions"].detect_fts() is not None


def test_all_is_idempotent(tmp_path):
    input_dir, output_dir = _make_dirs(tmp_path)
    _write_fixture_dumps(input_dir)
    db_path = tmp_path / "test.db"

    argv = [
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
    ]
    pipeline.main(argv=argv)
    pipeline.main(argv=argv)  # should not raise

    db = sqlite_utils.Database(str(db_path))
    assert db["isbn_lookup"].count == 2


def test_process_step_alone_produces_csvs(tmp_path):
    input_dir, output_dir = _make_dirs(tmp_path)
    _write_fixture_dumps(input_dir)

    pipeline.main(argv=[
        "process",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
    ])

    assert (output_dir / "ol_dump_authors_2025-05-01.csv").exists()
    assert (output_dir / "ol_dump_works_2025-05-01.csv").exists()
    assert (output_dir / "ol_dump_editions_2025-05-01.csv").exists()


def test_import_step_alone_against_existing_csvs(tmp_path):
    input_dir, output_dir = _make_dirs(tmp_path)
    _write_fixture_dumps(input_dir)
    db_path = tmp_path / "test.db"

    pipeline.main(argv=[
        "process", "--input-path", str(input_dir), "--output-path", str(output_dir),
    ])
    pipeline.main(argv=[
        "import", "--output-path", str(output_dir), "--db", str(db_path),
    ])

    db = sqlite_utils.Database(str(db_path))
    assert db["authors"].count == 1
    assert db["works"].count == 1
    assert db["editions"].count == 1


def test_index_step_alone_against_prepopulated_db(tmp_path):
    from tests.conftest import EDITION_ROWS

    db_path = tmp_path / "test.db"
    db = sqlite_utils.Database(str(db_path))
    db["editions"].insert_all(EDITION_ROWS)
    db.close()

    pipeline.main(argv=["index", "--db", str(db_path)])

    db = sqlite_utils.Database(str(db_path))
    assert db["isbn_lookup"].count > 0
    assert {"isbn": "0261102214", "ol_id": "OLedA1"} in list(db["isbn_lookup"].rows)


def test_fts_step_alone_enables_search(tmp_path):
    from tests.conftest import EDITION_ROWS

    db_path = tmp_path / "test.db"
    db = sqlite_utils.Database(str(db_path))
    db["editions"].insert_all(EDITION_ROWS)
    db.close()

    pipeline.main(argv=["fts", "--db", str(db_path)])

    db = sqlite_utils.Database(str(db_path))
    assert db["editions"].detect_fts() is not None


def test_optimize_step_alone_runs_without_error(tmp_path):
    from tests.conftest import EDITION_ROWS

    db_path = tmp_path / "test.db"
    db = sqlite_utils.Database(str(db_path))
    db["editions"].insert_all(EDITION_ROWS)
    db["editions"].enable_fts(["title"])
    db.close()

    pipeline.main(argv=["optimize", "--db", str(db_path)])

    db = sqlite_utils.Database(str(db_path))
    assert db["editions"].count == len(EDITION_ROWS)
