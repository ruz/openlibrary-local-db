import csv
import json
import sys

import process_data


def _line(key, data):
    return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])


def _write_dump(input_dir, filename, lines):
    (input_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_main(input_dir, output_dir, monkeypatch, extra_args=None):
    argv = ["process_data.py", "--input-path", str(input_dir), "--output-path", str(output_dir)]
    if extra_args:
        argv += extra_args
    monkeypatch.setattr(sys, "argv", argv)
    process_data.main()


def test_detect_dump_date_empty_dir(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    assert process_data.detect_dump_date(str(input_dir)) is None


def test_detect_dump_date_missing_dir(tmp_path):
    assert process_data.detect_dump_date(str(tmp_path / "does-not-exist")) is None


def test_detect_dump_date_partial_dump_types(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "ol_dump_works_2025-03-01.txt").write_text("", encoding="utf-8")
    assert process_data.detect_dump_date(str(input_dir)) is None


def test_detect_dump_date_most_recent_wins(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for dump_type in ("authors", "works", "editions"):
        (input_dir / f"ol_dump_{dump_type}_2024-01-01.txt").write_text("", encoding="utf-8")
        (input_dir / f"ol_dump_{dump_type}_2025-06-15.txt").write_text("", encoding="utf-8")
    assert process_data.detect_dump_date(str(input_dir)) == "2025-06-15"


def test_detect_dump_date_extension_filter(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    for dump_type in ("authors", "works", "editions"):
        (output_dir / f"ol_dump_{dump_type}_2025-06-15.csv").write_text("", encoding="utf-8")
    (output_dir / "ol_dump_authors_2025-06-15.txt").write_text("", encoding="utf-8")
    assert process_data.detect_dump_date(str(output_dir), extension="csv") == "2025-06-15"


def test_main_date_override(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    # A stale dump present alongside the one we want to pin via --date.
    _write_dump(input_dir, "ol_dump_works_2099-01-01.txt", [_line("/works/OL99W", {"title": "Future"})])
    _write_dump(input_dir, "ol_dump_works_2025-01-01.txt", [_line("/works/OL10W", {"title": "Pinned"})])

    _run_main(input_dir, output_dir, monkeypatch, extra_args=["--date", "2025-01-01"])

    assert (output_dir / "ol_dump_works_2025-01-01.csv").exists()
    assert not (output_dir / "ol_dump_works_2099-01-01.csv").exists()

    with open(output_dir / "ol_dump_works_2025-01-01.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";", quotechar="|"))
    assert rows[0]["title"] == "Pinned"


def test_main_no_dump_files_prints_message_and_returns(tmp_path, monkeypatch, capsys):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _run_main(input_dir, output_dir, monkeypatch)
    out = capsys.readouterr().out

    assert "nothing to process" in out
    assert list(output_dir.iterdir()) == []
