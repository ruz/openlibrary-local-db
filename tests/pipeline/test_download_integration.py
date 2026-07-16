import json

import sqlite_utils

import pipeline


def _line(key, data):
    return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])


def _write_fixture_dumps(input_dir, date_str):
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


def test_all_runs_download_step_and_threads_date_through(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"
    date_str = "2026-06-30"

    calls = []

    def fake_download_dumps(input_path, method="auto", date=None):
        calls.append((input_path, method, date))
        _write_fixture_dumps(input_dir, date_str)
        return date_str

    monkeypatch.setattr(pipeline.download_data, "download_dumps", fake_download_dumps)

    pipeline.main(argv=[
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
        "--method", "http",
    ])

    assert calls == [(str(input_dir), "http", None)]

    db = sqlite_utils.Database(str(db_path))
    assert db["authors"].count == 1
    assert db["works"].count == 1
    assert db["editions"].count == 1


def test_all_skips_download_step_when_flag_set(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"
    _write_fixture_dumps(input_dir, "2025-05-01")

    def fail_if_called(*a, **k):
        raise AssertionError("download_dumps should not be called with --skip-download")

    monkeypatch.setattr(pipeline.download_data, "download_dumps", fail_if_called)

    pipeline.main(argv=[
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
        "--skip-download",
    ])

    db = sqlite_utils.Database(str(db_path))
    assert db["authors"].count == 1


def test_all_auto_skips_download_when_dumps_already_present(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"
    _write_fixture_dumps(input_dir, "2025-05-01")

    def fail_if_called(*a, **k):
        raise AssertionError("download_dumps should not be called when dumps already exist in --input-path")

    monkeypatch.setattr(pipeline.download_data, "download_dumps", fail_if_called)

    pipeline.main(argv=[
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
    ])

    db = sqlite_utils.Database(str(db_path))
    assert db["authors"].count == 1


def test_all_downloads_when_pinned_date_does_not_match_existing_files(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    db_path = tmp_path / "test.db"
    _write_fixture_dumps(input_dir, "2025-05-01")

    calls = []

    def fake_download_dumps(input_path, method="auto", date=None):
        calls.append(date)
        _write_fixture_dumps(input_dir, "2026-06-30")
        return "2026-06-30"

    monkeypatch.setattr(pipeline.download_data, "download_dumps", fake_download_dumps)

    pipeline.main(argv=[
        "all",
        "--input-path", str(input_dir),
        "--output-path", str(output_dir),
        "--db", str(db_path),
        "--skip-env",
        "--date", "2026-06-30",
    ])

    assert calls == ["2026-06-30"]
    assert (output_dir / "ol_dump_authors_2026-06-30.csv").exists()


def test_download_command_alone_invokes_download_dumps(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    input_dir.mkdir()

    calls = []
    monkeypatch.setattr(
        pipeline.download_data, "download_dumps",
        lambda input_path, method="auto", date=None: calls.append((input_path, method, date)) or "2026-06-30",
    )

    pipeline.main(argv=["download", "--input-path", str(input_dir), "--method", "torrent"])

    assert calls == [(str(input_dir), "torrent", None)]
