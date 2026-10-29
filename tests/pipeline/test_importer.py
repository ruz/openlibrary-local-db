import csv
import sqlite3
from types import SimpleNamespace

import pipeline


EDITION_COLUMNS = (
    "ol_id", "title", "subtitle", "publish_date", "publish_year", "number_of_pages",
    "physical_format", "publishers", "isbn_10", "isbn_13", "subjects", "languages",
    "covers", "works", "authors", "author_names",
)


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=";", quotechar="|", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        writer.writerows(rows)


def run_import(output, database):
    return pipeline.run_import(SimpleNamespace(output_path=str(output), db=str(database), date="2026-09-30"))


def edition_row(index, *, title=None):
    return (
        f"OL{index:08d}M", title or f"Edition {index}", "", "2026", "2026", "300", "Hardcover",
        "[\"Publisher\"]", "[]", "[]", "[\"subject\"]", "[]", "[]", "[]", "[]", "[]",
    )


def test_import_batches_native_upsert_and_one_tail_statement(tmp_path, monkeypatch):
    output = tmp_path / "processed"
    output.mkdir()
    write_csv(
        output / "ol_dump_editions_2026-09-30.csv",
        EDITION_COLUMNS,
        [edition_row(index) for index in range(1007)],
    )
    database = tmp_path / "books.sqlite3"
    statements = []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced_connect)

    assert run_import(output, database) == "2026-09-30"

    upserts = [statement for statement in statements if "ON CONFLICT" in statement.upper()]
    assert len(upserts) == 2
    assert "INSERT INTO \"editions\"" in upserts[0]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1007
        assert connection.execute(
            "SELECT title FROM editions WHERE ol_id = ?", ("OL00001006M",)
        ).fetchone()[0] == "Edition 1006"


def test_existing_rows_update_in_place_and_keep_unimported_columns(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE works (ol_id TEXT PRIMARY KEY, title TEXT, operator_note TEXT)"
        )
        connection.execute("INSERT INTO works VALUES (?, ?, ?)", ("OL1W", "Before", "keep"))
        original_rowid = connection.execute(
            "SELECT rowid FROM works WHERE ol_id = 'OL1W'"
        ).fetchone()[0]
    write_csv(output / "ol_dump_works_2026-09-30.csv", ("ol_id", "title"), [("OL1W", "After")])

    run_import(output, database)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT rowid, title, operator_note FROM works WHERE ol_id = 'OL1W'"
        ).fetchone()
    assert row == (original_rowid, "After", "keep")


def test_new_csv_columns_are_added_to_existing_table(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE authors (ol_id TEXT PRIMARY KEY, name TEXT)")
    write_csv(
        output / "ol_dump_authors_2026-09-30.csv",
        ("ol_id", "name", "alternate_names"),
        [("OL1A", "Jane", "[\"J. Doe\"]")],
    )

    run_import(output, database)

    with sqlite3.connect(database) as connection:
        info = connection.execute("PRAGMA table_info(authors)").fetchall()
        row = connection.execute("SELECT name, alternate_names FROM authors WHERE ol_id='OL1A'").fetchone()
    assert info[-1][1:] == ("alternate_names", "TEXT", 0, None, 0)
    assert row == ("Jane", '["J. Doe"]')


def test_legacy_duplicates_keep_first_rowid_and_unique_index_is_reused(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE works (ol_id TEXT, title TEXT, operator_note TEXT)")
        connection.execute("INSERT INTO works VALUES ('OL1W', 'first', 'keep first')")
        first_rowid = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute("INSERT INTO works VALUES ('OL1W', 'second', 'drop second')")
        connection.execute("INSERT INTO works VALUES ('OL2W', 'untouched', 'keep other')")
        other_rowid = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    csv_path = output / "ol_dump_works_2026-09-30.csv"
    write_csv(csv_path, ("ol_id", "title"), [("OL1W", "updated"), ("OL3W", "new")])

    run_import(output, database)
    with sqlite3.connect(database) as connection:
        first = connection.execute(
            "SELECT rowid, title, operator_note FROM works WHERE ol_id='OL1W'"
        ).fetchone()
        other = connection.execute("SELECT rowid, title FROM works WHERE ol_id='OL2W'").fetchone()
        duplicates = connection.execute("SELECT COUNT(*) FROM works WHERE ol_id='OL1W'").fetchone()[0]
        unique_indexes_before = [
            row[1] for row in connection.execute("PRAGMA index_list(works)") if row[2]
        ]

    run_import(output, database)
    with sqlite3.connect(database) as connection:
        unique_indexes_after = [
            row[1] for row in connection.execute("PRAGMA index_list(works)") if row[2]
        ]
        assert connection.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 3
    assert first == (first_rowid, "updated", "keep first")
    assert other == (other_rowid, "untouched")
    assert duplicates == 1
    assert len(unique_indexes_before) == 1
    assert unique_indexes_after == unique_indexes_before


def test_conflicting_legacy_index_rolls_back_duplicate_cleanup(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE works (ol_id TEXT, title TEXT)")
        connection.executemany(
            "INSERT INTO works VALUES (?, ?)", [("OL1W", "first"), ("OL1W", "second")]
        )
        connection.execute("CREATE INDEX idx_works_ol_id_unique ON works(title)")
    write_csv(output / "ol_dump_works_2026-09-30.csv", ("ol_id", "title"), [("OL1W", "updated")])

    try:
        run_import(output, database)
    except sqlite3.OperationalError as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("conflicting unique-index name was accepted")

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM works WHERE ol_id='OL1W'").fetchone()[0] == 2
        assert connection.execute("SELECT title FROM works WHERE ol_id='OL1W' ORDER BY rowid").fetchall() == [
            ("first",), ("second",)
        ]


def test_long_csv_fields_and_csv_quoting_are_preserved(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    title = ("Long; | title\n" * 12000) + "end"
    write_csv(output / "ol_dump_editions_2026-09-30.csv", ("ol_id", "title"), [("OL1M", title)])

    run_import(output, database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT title FROM editions WHERE ol_id='OL1M'").fetchone()[0] == title


def test_variable_limit_caps_multirow_statement_size(tmp_path, monkeypatch):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    columns = ("ol_id", "title", "note")
    rows = [(f"OL{index}W", f"Title {index}", "note") for index in range(5)]
    write_csv(output / "ol_dump_works_2026-09-30.csv", columns, rows)
    statements = []
    connect = sqlite3.connect

    def limited_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 8)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", limited_connect)

    run_import(output, database)

    upserts = [statement for statement in statements if "ON CONFLICT" in statement.upper()]
    assert len(upserts) == 3
    assert sum(statement.upper().count("), (") + 1 for statement in upserts) == 5


def test_malformed_csv_rolls_back_only_uncommitted_batch_and_replay_is_safe(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    csv_path = output / "ol_dump_works_2026-09-30.csv"
    rows = [(f"OL{index:08d}W", f"Title {index}") for index in range(12003)]
    write_csv(csv_path, ("ol_id", "title"), rows)
    with csv_path.open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream, delimiter=";", quotechar="|").writerow(("broken-row",))

    try:
        run_import(output, database)
    except ValueError as error:
        assert "has 1 fields; expected 2" in str(error)
    else:
        raise AssertionError("malformed row was accepted")

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 10000

    write_csv(csv_path, ("ol_id", "title"), rows)
    run_import(output, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 12003
        assert connection.execute(
            "SELECT title FROM works WHERE ol_id='OL00012002W'"
        ).fetchone()[0] == "Title 12002"


def test_existing_wal_mode_is_preserved(tmp_path):
    output = tmp_path / "processed"
    output.mkdir()
    database = tmp_path / "books.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    write_csv(output / "ol_dump_works_2026-09-30.csv", ("ol_id", "title"), [("OL1W", "Title")])

    run_import(output, database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
