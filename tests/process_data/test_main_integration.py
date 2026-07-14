import csv
import json
import sys

import process_data

AUTHORS_FILE = "ol_dump_authors_2026-06-30.txt"
WORKS_FILE = "ol_dump_works_2026-06-30.txt"
EDITIONS_FILE = "ol_dump_editions_2026-06-30.txt"


def _line(key, data):
    return "\t".join(["type", key, "rev", "lastmod", json.dumps(data)])


def _write_dump(input_dir, filename, lines):
    (input_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(output_dir, filename):
    path = output_dir / filename
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar="|")
        return list(reader)


def _run_main(input_dir, output_dir, monkeypatch, extra_args=None):
    argv = ["process_data.py", "--input-path", str(input_dir), "--output-path", str(output_dir)]
    if extra_args:
        argv += extra_args
    monkeypatch.setattr(sys, "argv", argv)
    process_data.main()


def test_main_happy_path_all_tasks(tmp_path, monkeypatch, capsys):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, AUTHORS_FILE, [_line("/authors/OL1A", {
        "name": "Jane Doe", "birth_date": "1970", "death_date": "",
        "alternate_names": ["J. Doe"], "bio": "test bio", "photos": [-1, 5],
    })])
    _write_dump(input_dir, WORKS_FILE, [_line("/works/OL10W", {
        "title": "Test Work", "description": "desc",
        "authors": [{"author": {"key": "/authors/OL1A"}}],
        "subjects": ["Fantasy"], "subject_people": [], "subject_places": [],
        "covers": [1], "series": [{"series": {"key": "/series/OL1S"}}],
    })])
    _write_dump(input_dir, EDITIONS_FILE, [_line("/books/OLedX1M", {
        "title": "Test Edition", "subtitle": "", "publish_date": "1999",
        "number_of_pages": 100, "physical_format": "Hardcover",
        "publishers": ["Pub"], "isbn_10": ["0-261-10221-4"], "isbn_13": [],
        "subjects": ["Fantasy"], "languages": [{"key": "/languages/eng"}],
        "covers": [-1, 2], "works": [{"key": "/works/OL10W"}],
        "authors": [{"key": "/authors/OL1A"}],
    })])

    _run_main(input_dir, output_dir, monkeypatch)
    out = capsys.readouterr().out

    assert (output_dir / "ol_dump_authors_2026-06-30.csv").exists()
    assert (output_dir / "ol_dump_works_2026-06-30.csv").exists()
    assert (output_dir / "ol_dump_editions_2026-06-30.csv").exists()

    authors_rows = _read_csv(output_dir, "ol_dump_authors_2026-06-30.csv")
    assert list(authors_rows[0].keys()) == process_data.tasks[0]["fields"]
    assert len(authors_rows) == 1

    assert "authors: processed 1 rows, skipped 0 malformed rows." in out
    assert "works: processed 1 rows, skipped 0 malformed rows." in out
    assert "editions: processed 1 rows, skipped 0 malformed rows." in out
    assert "All tasks complete." in out


def test_main_author_lookup_populates_edition_author_names(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, AUTHORS_FILE, [_line("/authors/OL1A", {"name": "Jane Doe"})])
    _write_dump(input_dir, WORKS_FILE, [_line("/works/OL10W", {"title": "Test Work"})])
    _write_dump(input_dir, EDITIONS_FILE, [_line("/books/OLedX1M", {
        "title": "Test Edition",
        "authors": [{"key": "/authors/OL1A"}],
    })])

    _run_main(input_dir, output_dir, monkeypatch)

    editions_rows = _read_csv(output_dir, "ol_dump_editions_2026-06-30.csv")
    assert json.loads(editions_rows[0]["author_names"]) == ["Jane Doe"]


def test_main_skips_malformed_json_row(tmp_path, monkeypatch, capsys):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    valid_line = _line("/works/OL10W", {"title": "Good Row"})
    malformed_line = "\t".join(["type", "/works/OL11W", "rev", "lastmod", "{not json"])
    _write_dump(input_dir, WORKS_FILE, [valid_line, malformed_line])

    _run_main(input_dir, output_dir, monkeypatch)
    out = capsys.readouterr().out

    rows = _read_csv(output_dir, "ol_dump_works_2026-06-30.csv")
    assert len(rows) == 1
    assert "works: processed 1 rows, skipped 1 malformed rows." in out


def test_main_skips_short_rows(tmp_path, monkeypatch, capsys):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    valid_line = _line("/works/OL10W", {"title": "Good Row"})
    short_line = "type\t/works/OL11W\trev"
    _write_dump(input_dir, WORKS_FILE, [valid_line, short_line])

    _run_main(input_dir, output_dir, monkeypatch)
    out = capsys.readouterr().out

    rows = _read_csv(output_dir, "ol_dump_works_2026-06-30.csv")
    assert len(rows) == 1
    assert "works: processed 1 rows, skipped 0 malformed rows." in out


def test_main_skips_missing_input_file(tmp_path, monkeypatch, capsys):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, AUTHORS_FILE, [_line("/authors/OL1A", {"name": "Jane Doe"})])
    _write_dump(input_dir, WORKS_FILE, [_line("/works/OL10W", {"title": "Test Work"})])
    # editions dump intentionally omitted

    _run_main(input_dir, output_dir, monkeypatch)
    out = capsys.readouterr().out

    assert f"Skipping {EDITIONS_FILE}: File not found." in out
    assert not (output_dir / "ol_dump_editions_2026-06-30.csv").exists()
    assert (output_dir / "ol_dump_authors_2026-06-30.csv").exists()
    assert (output_dir / "ol_dump_works_2026-06-30.csv").exists()


def test_main_limit_caps_rows_per_task(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    author_lines = [_line(f"/authors/OL{i}A", {"name": f"Author {i}"}) for i in range(5)]
    edition_lines = [_line(f"/books/OLed{i}M", {"title": f"Edition {i}"}) for i in range(5)]
    _write_dump(input_dir, AUTHORS_FILE, author_lines)
    _write_dump(input_dir, EDITIONS_FILE, edition_lines)

    _run_main(input_dir, output_dir, monkeypatch, extra_args=["--limit", "2"])

    assert len(_read_csv(output_dir, "ol_dump_authors_2026-06-30.csv")) == 2
    assert len(_read_csv(output_dir, "ol_dump_editions_2026-06-30.csv")) == 2


def test_main_bio_and_description_dict_vs_string_variants(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, AUTHORS_FILE, [
        _line("/authors/OL1A", {"name": "Dict Bio", "bio": {"value": "dict text"}}),
        _line("/authors/OL2A", {"name": "String Bio", "bio": "plain text"}),
    ])
    _write_dump(input_dir, WORKS_FILE, [
        _line("/works/OL10W", {"title": "Dict Desc", "description": {"value": "dict desc"}}),
        _line("/works/OL11W", {"title": "String Desc", "description": "plain desc"}),
    ])

    _run_main(input_dir, output_dir, monkeypatch)

    authors_rows = _read_csv(output_dir, "ol_dump_authors_2026-06-30.csv")
    assert authors_rows[0]["bio"] == "dict text"
    assert authors_rows[1]["bio"] == "plain text"

    works_rows = _read_csv(output_dir, "ol_dump_works_2026-06-30.csv")
    assert works_rows[0]["description"] == "dict desc"
    assert works_rows[1]["description"] == "plain desc"


def test_main_works_author_ref_shape_variants(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, WORKS_FILE, [
        _line("/works/OL10W", {"title": "Nested", "authors": [{"author": {"key": "/authors/OL1A"}}]}),
        _line("/works/OL11W", {"title": "Flat", "authors": [{"key": "/authors/OL2A"}]}),
    ])

    _run_main(input_dir, output_dir, monkeypatch)

    rows = _read_csv(output_dir, "ol_dump_works_2026-06-30.csv")
    assert json.loads(rows[0]["authors"]) == ["OL1A"]
    assert json.loads(rows[1]["authors"]) == ["OL2A"]


def test_main_series_extraction(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, WORKS_FILE, [_line("/works/OL10W", {
        "title": "Series Work",
        "series": [{"series": {"key": "/series/OL1S"}}],
    })])

    _run_main(input_dir, output_dir, monkeypatch)

    rows = _read_csv(output_dir, "ol_dump_works_2026-06-30.csv")
    assert json.loads(rows[0]["series"]) == ["OL1S"]


def test_main_editions_languages_and_works_refs(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, EDITIONS_FILE, [_line("/books/OLedX1M", {
        "title": "Ref Edition",
        "languages": [{"key": "/languages/eng"}],
        "works": [{"key": "/works/OL10W"}],
    })])

    _run_main(input_dir, output_dir, monkeypatch)

    rows = _read_csv(output_dir, "ol_dump_editions_2026-06-30.csv")
    assert json.loads(rows[0]["languages"]) == ["eng"]
    assert json.loads(rows[0]["works"]) == ["OL10W"]


def test_main_isbn_normalization_applied(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, EDITIONS_FILE, [_line("/books/OLedX1M", {
        "title": "ISBN Edition",
        "isbn_10": ["0-261-10221-4"],
        "isbn_13": ["978-0-261-10221-4"],
    })])

    _run_main(input_dir, output_dir, monkeypatch)

    rows = _read_csv(output_dir, "ol_dump_editions_2026-06-30.csv")
    assert json.loads(rows[0]["isbn_10"]) == ["0261102214"]
    assert json.loads(rows[0]["isbn_13"]) == ["9780261102214"]


def test_main_photos_and_covers_filtered(tmp_path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    _write_dump(input_dir, AUTHORS_FILE, [_line("/authors/OL1A", {
        "name": "Photo Author", "photos": [-1, 12345],
    })])
    _write_dump(input_dir, EDITIONS_FILE, [_line("/books/OLedX1M", {
        "title": "Cover Edition", "covers": [-1, 2],
    })])

    _run_main(input_dir, output_dir, monkeypatch)

    authors_rows = _read_csv(output_dir, "ol_dump_authors_2026-06-30.csv")
    assert json.loads(authors_rows[0]["photos"]) == [12345]

    editions_rows = _read_csv(output_dir, "ol_dump_editions_2026-06-30.csv")
    assert json.loads(editions_rows[0]["covers"]) == [2]
