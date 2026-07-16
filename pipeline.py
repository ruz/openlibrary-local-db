import argparse
import csv
import os
import shutil

from dotenv import load_dotenv
import sqlite_utils

import download_data
import overrides
import process_data

load_dotenv()

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


def run_download(args):
    if args.skip_download:
        print("Skipping download step (--skip-download).")
        return None
    date_str = download_data.download_dumps(args.input_path, method=args.method, date=args.date)
    if date_str is None:
        print("Download step could not determine a dump date; nothing downloaded.")
    return date_str


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


def _dedupe_by_ol_id(db, table):
    """Collapse pre-existing duplicate ol_id rows (from the old insert_all-based
    import) so upsert_all's implicit unique index on ol_id can be created."""
    db.execute(
        f"DELETE FROM {table} WHERE rowid NOT IN "
        f"(SELECT MIN(rowid) FROM {table} GROUP BY ol_id)"
    )


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
        if table in db.table_names() and "ol_id" not in db[table].pks:
            _dedupe_by_ol_id(db, table)
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";", quotechar="|")
            db[table].upsert_all(reader, pk="ol_id", batch_size=IMPORT_BATCH_SIZE, alter=True)
        print(f"Imported {table} into {args.db}.")
    return date_str


BROWSE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_editions_publish_year ON editions(publish_year);
CREATE INDEX IF NOT EXISTS idx_editions_physical_format ON editions(physical_format);
CREATE INDEX IF NOT EXISTS idx_editions_title_nocase ON editions(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_works_title_nocase ON works(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_authors_name_nocase ON authors(name COLLATE NOCASE);
"""


def run_index(args):
    db = sqlite_utils.Database(args.db)
    db.executescript(ISBN_LOOKUP_SQL)
    db["isbn_lookup"].create_index(["isbn"], unique=True, if_not_exists=True)
    for table in TABLE_TYPES:
        if table in db.table_names() and "ol_id" not in db[table].pks:
            db[table].create_index(["ol_id"], if_not_exists=True)
    db.executescript(BROWSE_INDEXES_SQL)
    print("Built isbn_lookup table, ol_id indexes, and browse indexes.")


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
    if args.skip_download:
        print("Skipping download step (--skip-download).")
        date_str = resolve_date(args)
    else:
        existing_date = process_data.detect_dump_date(args.input_path)
        if existing_date and (args.date is None or args.date == existing_date):
            print(f"Dump files already present in {args.input_path} (date {existing_date}); skipping download.")
            date_str = existing_date
        else:
            date_str = run_download(args)

    if date_str is None:
        print("No dump files found in --input-path; nothing to do.")
        return

    run_process(args, date_str=date_str)
    run_import(args, date_str=date_str)
    run_overrides_sync(args)
    run_index(args)
    run_fts(args)
    run_optimize(args)

    if not args.skip_env:
        update_env_file(args.db, date_str)

    print("Pipeline complete.")


def _require_overrides_db(args):
    ov_conn = overrides.get_overrides_db(args.overrides_db)
    if ov_conn is None:
        raise SystemExit("OVERRIDES_DB is not set; pass --overrides-db or set the OVERRIDES_DB env var.")
    return ov_conn


def run_overrides_list(args):
    ov_conn = _require_overrides_db(args)
    rows = overrides.list_overrides(ov_conn, status=args.status, entity_type=args.entity_type)
    if not rows:
        print("No overrides found.")
        return
    for row in rows:
        print(f"{row['entity_type']}/{row['ol_id']} [{row['status']}] patch={row['patch']}")


def run_overrides_set(args):
    ov_conn = _require_overrides_db(args)
    db = sqlite_utils.Database(args.db)
    if args.entity_type not in db.table_names():
        raise SystemExit(f"Table '{args.entity_type}' not found in {args.db}.")
    rows = list(db[args.entity_type].rows_where("ol_id = ?", [args.ol_id]))
    if not rows:
        raise SystemExit(f"No {args.entity_type} record found with ol_id={args.ol_id!r} in {args.db}.")
    base_row = rows[0]
    patch = {}
    for field_kv in args.field:
        key, _, value = field_kv.partition("=")
        patch[key] = value
    dump_date = args.date or os.getenv("OLDUMP_DATE") or ""
    overrides.set_override(ov_conn, args.entity_type, args.ol_id, patch, base_row, dump_date, note=args.note)
    print(f"Set override for {args.entity_type}/{args.ol_id}: {patch}")


def run_overrides_discard(args):
    ov_conn = _require_overrides_db(args)
    removed = overrides.discard_override(ov_conn, args.entity_type, args.ol_id)
    print("Discarded." if removed else "No override found.")


def run_overrides_sync(args):
    ov_conn = overrides.get_overrides_db(args.overrides_db)
    if ov_conn is None:
        return
    result = overrides.sync_overrides(ov_conn, args.db)
    print(f"Overrides sync complete: {result['stale']} stale, {result['orphaned']} orphaned.")


def run_overrides_resolve(args):
    ov_conn = _require_overrides_db(args)
    if args.keep_mine:
        action = "keep-mine"
    elif args.accept_upstream:
        action = "accept-upstream"
    else:
        action = "discard"
    changed = overrides.resolve_override(ov_conn, args.entity_type, args.ol_id, action)
    print("Resolved." if changed else "No override found.")


def run_overrides_export(args):
    ov_conn = _require_overrides_db(args)
    count = overrides.export_overrides(ov_conn, args.output, status=args.status)
    print(f"Exported {count} override(s) to {args.output}.")


def run_overrides_mark_submitted(args):
    ov_conn = _require_overrides_db(args)
    changed = overrides.mark_submitted(ov_conn, args.entity_type, args.ol_id)
    print("Marked submitted." if changed else "No override found.")


def run_overrides_clear(args):
    if not args.yes:
        raise SystemExit("Refusing to clear overrides without --yes.")
    ov_conn = _require_overrides_db(args)
    overrides.clear_overrides(ov_conn)
    print("Cleared all overrides.")


def run_overrides_suggestions_list(args):
    ov_conn = _require_overrides_db(args)
    rows = overrides.list_suggestions(ov_conn, status=args.status, entity_type=args.entity_type)
    if not rows:
        print("No suggestions found.")
        return
    for row in rows:
        print(
            f"#{row['id']} {row['entity_type']}/{row['ol_id']} [{row['status']}] "
            f"action={row['action']} patch={row['patch']} note={row['note']!r}"
        )


def run_overrides_suggestions_approve(args):
    ov_conn = _require_overrides_db(args)
    suggestion = overrides.get_suggestion(ov_conn, args.suggestion_id)
    if suggestion is None or suggestion["status"] != "pending":
        raise SystemExit(f"No pending suggestion with id={args.suggestion_id}.")

    base_row = None
    if suggestion["action"] == "patch":
        db = sqlite_utils.Database(args.db)
        rows = list(db[suggestion["entity_type"]].rows_where("ol_id = ?", [suggestion["ol_id"]]))
        if not rows:
            raise SystemExit(f"{suggestion['ol_id']} no longer exists in {args.db}; cannot approve.")
        base_row = rows[0]

    dump_date = args.date or os.getenv("OLDUMP_DATE") or ""
    overrides.approve_suggestion(ov_conn, args.suggestion_id, base_row, dump_date)
    print(f"Approved suggestion #{args.suggestion_id}.")


def run_overrides_suggestions_reject(args):
    ov_conn = _require_overrides_db(args)
    rejected = overrides.reject_suggestion(ov_conn, args.suggestion_id)
    print(f"Rejected suggestion #{args.suggestion_id}." if rejected else "No pending suggestion found.")


SUGGESTIONS_HANDLERS = {
    "list": run_overrides_suggestions_list,
    "approve": run_overrides_suggestions_approve,
    "reject": run_overrides_suggestions_reject,
}


def run_overrides_suggestions(args):
    SUGGESTIONS_HANDLERS[args.suggestions_command](args)


OVERRIDES_HANDLERS = {
    "list": run_overrides_list,
    "set": run_overrides_set,
    "discard": run_overrides_discard,
    "sync": run_overrides_sync,
    "resolve": run_overrides_resolve,
    "export": run_overrides_export,
    "mark-submitted": run_overrides_mark_submitted,
    "clear": run_overrides_clear,
    "suggestions": run_overrides_suggestions,
}


def run_overrides(args):
    OVERRIDES_HANDLERS[args.overrides_command](args)


STEP_HANDLERS = {
    "download": run_download,
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
    common.add_argument("--method", choices=["auto", "torrent", "http"], default="auto",
                         help="Transport for the download step: 'auto' tries BitTorrent first and "
                              "falls back to HTTP, 'torrent' forces BitTorrent, 'http' forces direct "
                              "HTTP download (default: auto; only used by download/all)")
    common.add_argument("--skip-download", action="store_true",
                         help="Don't download dump files when running 'all'; use files already "
                              "present in --input-path (only used by all)")
    common.add_argument("--overrides-db", default=os.getenv("OVERRIDES_DB"),
                         help="Path to the overrides SQLite database (default: OVERRIDES_DB env var; "
                              "leave unset to keep the overrides feature disabled)")

    parser = argparse.ArgumentParser(description="Automate the OpenLibrary DB build pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("download", parents=[common],
                           help="Download the latest authors/works/editions dumps into --input-path.")
    subparsers.add_parser("process", parents=[common], help="Process raw dumps into CSV files.")
    subparsers.add_parser("import", parents=[common], help="Import processed CSVs into the SQLite database.")
    subparsers.add_parser("index", parents=[common], help="Build the isbn_lookup table and ol_id indexes.")
    subparsers.add_parser("fts", parents=[common], help="Enable full-text search on editions.")
    subparsers.add_parser("optimize", parents=[common], help="Optimize the SQLite database.")
    subparsers.add_parser("all", parents=[common],
                           help="Run the full pipeline end-to-end (download, process, import, index, fts, optimize).")

    overrides_parser = subparsers.add_parser(
        "overrides", parents=[common],
        help="Manage persistent local corrections to imported records (opt-in; requires --overrides-db).",
    )
    overrides_sub = overrides_parser.add_subparsers(dest="overrides_command", required=True)

    list_p = overrides_sub.add_parser("list", help="List stored overrides.")
    list_p.add_argument("--status", default=None,
                         choices=["active", "stale", "orphaned", "submitted"])
    list_p.add_argument("--entity-type", default=None, choices=overrides.ENTITY_TYPES)

    set_p = overrides_sub.add_parser("set", help="Create or update an override for a record.")
    set_p.add_argument("entity_type", choices=overrides.ENTITY_TYPES)
    set_p.add_argument("ol_id")
    set_p.add_argument("--field", action="append", required=True, metavar="KEY=VALUE",
                        help="Field to override, e.g. --field title='Fixed Title'. May be repeated.")
    set_p.add_argument("--note", default=None)

    discard_p = overrides_sub.add_parser("discard", help="Remove a single override.")
    discard_p.add_argument("entity_type", choices=overrides.ENTITY_TYPES)
    discard_p.add_argument("ol_id")

    overrides_sub.add_parser("sync", help="Re-check active overrides against the current base DB for drift.")

    resolve_p = overrides_sub.add_parser("resolve", help="Reconcile a stale or orphaned override.")
    resolve_p.add_argument("entity_type", choices=overrides.ENTITY_TYPES)
    resolve_p.add_argument("ol_id")
    resolve_group = resolve_p.add_mutually_exclusive_group(required=True)
    resolve_group.add_argument("--keep-mine", action="store_true", help="Keep my edit as-is.")
    resolve_group.add_argument("--accept-upstream", action="store_true",
                                help="Defer to OpenLibrary's new value; drops the override.")
    resolve_group.add_argument("--discard", action="store_true", help="Abandon the correction entirely.")

    export_p = overrides_sub.add_parser(
        "export", help="Export overrides as JSON for manual submission to OpenLibrary.")
    export_p.add_argument("--status", default="active")
    export_p.add_argument("--output", required=True)

    mark_p = overrides_sub.add_parser("mark-submitted", help="Flag an override as already submitted upstream.")
    mark_p.add_argument("entity_type", choices=overrides.ENTITY_TYPES)
    mark_p.add_argument("ol_id")

    clear_p = overrides_sub.add_parser("clear", help="Delete all stored overrides.")
    clear_p.add_argument("--yes", action="store_true", help="Confirm the destructive clear.")

    suggestions_parser = overrides_sub.add_parser(
        "suggestions", help="Moderate suggestions submitted anonymously via the API.")
    suggestions_sub = suggestions_parser.add_subparsers(dest="suggestions_command", required=True)

    suggestions_list_p = suggestions_sub.add_parser("list", help="List stored suggestions.")
    suggestions_list_p.add_argument("--status", default=None,
                                     choices=["pending", "approved", "rejected"])
    suggestions_list_p.add_argument("--entity-type", default=None, choices=overrides.ENTITY_TYPES)

    suggestions_approve_p = suggestions_sub.add_parser(
        "approve", help="Approve a pending suggestion, promoting it into a real override.")
    suggestions_approve_p.add_argument("suggestion_id", type=int)

    suggestions_reject_p = suggestions_sub.add_parser("reject", help="Reject a pending suggestion.")
    suggestions_reject_p.add_argument("suggestion_id", type=int)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "overrides":
        run_overrides(args)
    else:
        STEP_HANDLERS[args.command](args)


if __name__ == "__main__":
    main()
