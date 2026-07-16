import argparse
import csv
import os
import shutil

import sqlite_utils

import process_data

DEFAULT_INPUT_PATH = "./data/unprocessed/"
DEFAULT_OUTPUT_PATH = "./data/processed/"
DEFAULT_DB = "test.db"

IMPORT_BATCH_SIZE = 5000

TABLE_TYPES = ("authors", "works", "editions")

ISBN_LOOKUP_SQL = """
DROP TABLE IF EXISTS isbn_lookup;
CREATE TABLE isbn_lookup AS
SELECT value AS isbn, MIN(ol_id) AS ol_id
FROM editions, json_each(isbn_10)
GROUP BY value
UNION
SELECT value AS isbn, MIN(ol_id) AS ol_id
FROM editions, json_each(isbn_13)
GROUP BY value
"""


def resolve_date(args):
    return args.date or process_data.detect_dump_date(args.input_path)


def resolve_csv_date(args):
    return args.date or process_data.detect_dump_date(args.output_path, extension="csv")


def run_process(args, date_str=None):
    date_str = date_str or resolve_date(args)
    if date_str is None:
        print("No dump files found; skipping process step.")
        return None

    process_data.main(argv=[
        "--input-path", args.input_path,
        "--output-path", args.output_path,
        "--date", date_str,
        *(["--limit", str(args.limit)] if args.limit is not None else []),
    ])
    return date_str


def run_import(args, date_str=None):
    date_str = date_str or resolve_csv_date(args)
    if date_str is None:
        print("No processed CSV files found; skipping import step.")
        return None

    db = sqlite_utils.Database(args.db)
    for table in TABLE_TYPES:
        csv_path = os.path.join(args.output_path, f"ol_dump_{table}_{date_str}.csv")
        if not os.path.exists(csv_path):
            print(f"Skipping {table} import: {csv_path} not found.")
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";", quotechar="|")
            db[table].insert_all(reader, batch_size=IMPORT_BATCH_SIZE, alter=True)
        print(f"Imported {table} into {args.db}.")
    return date_str


def run_index(args):
    db = sqlite_utils.Database(args.db)
    db.executescript(ISBN_LOOKUP_SQL)
    db["isbn_lookup"].create_index(["isbn"], unique=True, if_not_exists=True)
    for table in TABLE_TYPES:
        if table in db.table_names():
            db[table].create_index(["ol_id"], if_not_exists=True)
    print("Built isbn_lookup table and ol_id indexes.")


def run_fts(args):
    db = sqlite_utils.Database(args.db)
    db["editions"].enable_fts(["title", "isbn_10", "isbn_13", "author_names"], replace=True)
    print("Enabled full-text search on editions.")


def run_optimize(args):
    db = sqlite_utils.Database(args.db)
    for table in db.table_names():
        if db[table].detect_fts():
            db[table].optimize()
    db.conn.commit()
    db.vacuum()
    print(f"Optimized {args.db}.")


def update_env_file(db_path, date_str, env_path=".env", example_path=".env.example"):
    if not os.path.exists(env_path):
        if os.path.exists(example_path):
            shutil.copyfile(example_path, env_path)
        else:
            open(env_path, "a", encoding="utf-8").close()

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updates = {"OL_DB": db_path, "OLDUMP_DATE": date_str}
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched_key = next(
            (key for key in updates
             if stripped.startswith(f"{key}=") or stripped.startswith(f"#{key}=")),
            None,
        )
        if matched_key:
            new_lines.append(f'{matched_key}="{updates[matched_key]}"\n')
            updated_keys.add(matched_key)
        else:
            new_lines.append(line)

    for key in updates:
        if key not in updated_keys:
            new_lines.append(f'{key}="{updates[key]}"\n')

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"Updated {env_path} with OL_DB and OLDUMP_DATE.")


def run_all(args):
    date_str = resolve_date(args)
    if date_str is None:
        print("No dump files found in --input-path; nothing to do.")
        return

    run_process(args, date_str=date_str)
    run_import(args, date_str=date_str)
    run_index(args)
    run_fts(args)
    run_optimize(args)

    if not args.skip_env:
        update_env_file(args.db, date_str)

    print("Pipeline complete.")


STEP_HANDLERS = {
    "process": run_process,
    "import": run_import,
    "index": run_index,
    "fts": run_fts,
    "optimize": run_optimize,
    "all": run_all,
}


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input-path", default=DEFAULT_INPUT_PATH,
                         help=f"Directory containing the raw dump files (default: {DEFAULT_INPUT_PATH})")
    common.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH,
                         help=f"Directory containing/receiving processed CSV files (default: {DEFAULT_OUTPUT_PATH})")
    common.add_argument("--db", default=DEFAULT_DB,
                         help=f"Path to the SQLite database file (default: {DEFAULT_DB})")
    common.add_argument("--date", default=None,
                         help="OL dump date (YYYY-MM-DD); auto-detected from filenames if omitted")
    common.add_argument("--limit", type=int, default=None,
                         help="Stop after processing this many rows per dump file (only used by process/all)")
    common.add_argument("--skip-env", action="store_true",
                         help="Don't create/update the .env file (only used by all)")

    parser = argparse.ArgumentParser(description="Automate the OpenLibrary DB build pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("process", parents=[common], help="Process raw dumps into CSV files.")
    subparsers.add_parser("import", parents=[common], help="Import processed CSVs into the SQLite database.")
    subparsers.add_parser("index", parents=[common], help="Build the isbn_lookup table and ol_id indexes.")
    subparsers.add_parser("fts", parents=[common], help="Enable full-text search on editions.")
    subparsers.add_parser("optimize", parents=[common], help="Optimize the SQLite database.")
    subparsers.add_parser("all", parents=[common], help="Run the full pipeline end-to-end.")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    STEP_HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
