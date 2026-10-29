# Improve the Open Library SQLite importer

## User input

Use the user's fork at `ruz/openlibrary-local-db`, implement the measured SQLite import improvements on a branch, push them, and restart the laptop import. Do not download Open Library dumps to the development machine.

Use the retained processed CSV for importer changes and tests. Keep corrections and suggestions unchanged. The hostings repository owns deployment and import checkpoints; this fork owns importer code. Use the measured native SQLite UPSERT approach with prepared-statement reuse, multi-row SQL, and ten statements per transaction. Do not add plain-INSERT comparisons, new dependencies, or a tuning matrix.

## Description

The current pipeline imports processed CSV with `sqlite-utils.upsert_all`. The 100,000-row host benchmark showed that native SQLite UPSERTs with a 1,000-row SQL statement and ten statements per transaction reduced median time from 1.188 seconds (one-row UPSERT with CPython's statement cache) to 0.593 seconds. The measured run used only 100,000 edition rows, no secondary indexes, and warm OS cache; it does not predict full-dump duration.

This change replaces only the CSV import implementation. It uses Python's standard `sqlite3` module and native `INSERT ... ON CONFLICT DO UPDATE`, reuses the same SQL statement text, and commits after ten statements. Keep the current `pipeline import` and `pipeline all` commands and data behavior. The deployment remains in the hostings project; the full import is restarted there after the improved importer passes a 100,000-row laptop check. No real dump is copied to or downloaded on the development machine.

| Choice | Status | Effect |
| --- | --- | --- |
| Native UPSERT | Benchmark-selected | Use raw `sqlite3`; update imported columns in place on `ol_id` conflict. |
| Statement shape | Benchmark-selected | Use up to 1,000 CSV rows per multi-value statement, with one tail statement when needed; reuse stable SQL text and use `cached_statements=128`. |
| Transaction cadence | Benchmark-selected | Commit after ten UPSERT statements (nominally 10,000 rows on the pinned SQLite build). |
| Durability and cache | Benchmark-selected | Keep SQLite `DELETE` journal, `FULL` synchronization, and the default roughly 2 MiB page cache. WAL/NORMAL showed only a small median difference and more measured writes; a 256 MiB cache did not help. |
| Compatibility | Required | Preserve current CLI, CSV format, table/column behavior, rowids, unrelated columns, and restart-safe committed prefixes. |
| Data location | User constraint | Use small temporary fixtures for repository tests; use the retained laptop CSV for the separate 100,000-row check. Do not download dumps locally. |

## Implementation details

At project start, `pipeline.py` calls `sqlite_utils.Database(args.db)` and `upsert_all(..., pk="ol_id", batch_size=5000, alter=True)` for each available authors, works, and editions CSV. It reads UTF-8 CSV with `;` delimiter and `|` quote character. It skips a missing table CSV and resolves the CSV date through the existing `--date` and filename-detection behavior. `pipeline import` and `pipeline all` are existing public commands.

An untouched baseline run with `/private/tmp/openlibrary-importer-venv/bin/python` (Python 3.14.6 and `sqlite-utils` 3.39.1) produced 198 passed and 13 failed tests. All 13 failures are in `tests/process_data/test_date_detection.py` and `tests/process_data/test_main_integration.py`. Those tests expect partial dump files to auto-detect a date, but the existing processor requires a complete three-file snapshot for date detection. Keep `process_data.py` byte-identical so the existing laptop CSV checkpoint remains reusable. Repair only the stale test fixtures and assertions: pass explicit `--date` when a processor fixture contains partial files, test date detection with a complete snapshot, and assert that an incomplete set does not resolve a date. Do not change processor behavior.

The laptop's interrupted database was recovered and inspected during preflight: authors has 7 columns, works 9, and editions 16; all columns are `TEXT`, `ol_id` is the single primary key, and each table has only its primary-key index. There are no legacy non-key indexes to preserve in this database, but the importer must keep its legacy duplicate cleanup behavior for other existing databases. The aligned local test environment has pytest 9.2 and the repository dependencies within constraints; the repository has no configured linter or CI workflow.

Change only the importer path in `pipeline.py`. Keep `sqlite-utils` for index, FTS, optimize, and other stages. Stream `csv.DictReader` rows and hold only one bounded batch. Use `ol_id TEXT PRIMARY KEY` for new tables, keep input values as text, add newly observed columns to existing tables, and update only columns present in the CSV. Do not use `REPLACE` or `WITHOUT ROWID`; preserve SQLite rowids and existing columns outside the import projection. The only other code-adjacent edits are the scoped stale date-detection test fixture/assertion repairs described above; leave `process_data.py` unchanged.

Build native UPSERT statements with bound parameters. Use up to 1,000 rows per statement and cap this number at the connection's actual SQLite variable limit divided by the number of CSV columns. Do not assume the old `sqlite-utils` 999-variable limit. Reuse the same full-batch SQL string and prepare one tail shape when a remainder exists. Commit each ten statements; if a failure occurs, roll back the current uncommitted transaction and leave already committed chunks available. Since UPSERT is idempotent, a retry can replay that prefix safely. Report committed progress per ten statements and each table's final elapsed time and row count.

When an existing table has no `ol_id` primary key, preserve the current migration behavior: keep the first row by `rowid` for each `ol_id`, then establish uniqueness with an index. Do not replace existing rows, which would change rowids. Preserve behavior when new CSV columns appear and when unrelated table columns are present.

The benchmark recorded medians of 1.187734 seconds for cached one-row UPSERTs, 0.830744 seconds for 1,000-row statements with one query per transaction, and 0.593145 seconds when ten such queries share a transaction. WAL/NORMAL measured 0.568194 seconds, about 4% lower, while kernel writes rose; three serial runs are not enough to treat that as a proven gain. A 256 MiB cache measured 0.578927 seconds. The current importer already benefits from CPython's default prepared-statement cache, so use the cached one-row result as the relevant baseline. Full benchmark evidence is in the hostings worktree at [`openlibrary-experiment.md`](/Users/ruz/projs/hostings/worktrees/openlibrary-experiment/docs/projects/openlibrary-experiment.md) and [`2026-10-29-upsert.json`](/Users/ruz/projs/hostings/worktrees/openlibrary-experiment/experiments/openlibrary-local-db/results/2026-10-29-upsert.json).

## Compatibility and rollout

Keep all existing pipeline command names and arguments, including `--input-path`, `--output-path`, `--db`, `--date`, `--limit`, and `--skip-download`. Do not change download, processing, index, FTS, optimize, API, corrections, or suggestions behavior. The importer change runs in the existing in-place database. Hostings owns copying the branch to the laptop, running the 100,000-row check against the retained processed CSV, and restarting the stopped import only after that check succeeds. The development worktree must not contain a full Open Library dataset.

## Tasks

| Branch | Parent / PR target | Subject | Status |
| --- | --- | --- | --- |
| `importer-performance-1` | actual parent `49b8bd4b66daad0ea35c938c762c5ac063c92721` / PR target `main` | Plan importer improvement | Ready for review; not published |
| `importer-performance-2` | planned predecessor `importer-performance-1` / planned PR target `importer-performance-1` | Implement and verify native SQLite importer | Planned |

### Unit 1: plan the importer change

Outcome and boundary: this documentation unit records the measured choices, importer compatibility requirements, and verification scope. It does not change importer behavior or run an import.

Acceptance: the plan distinguishes repository and deployment ownership, records the six-variant evidence that supports the selected configuration, and defines tests without requiring real dump data locally.

- [x] Add Cadence documentation indexes and this project plan.

### Unit 2: implement the measured importer

Depends on Unit 1. Outcome and boundary: the existing pipeline imports CSV with standard-library `sqlite3`, native UPSERT, bounded multi-row statements, and committed-prefix recovery. Other pipeline stages and host deployment remain unchanged.

Acceptance: focused temporary-database tests cover fresh and existing tables, update/insert behavior, stable rowids and unrelated columns, schema evolution, legacy duplicate cleanup, variable-limit capping, long CSV fields, tail batches, ten-query commits, malformed input rollback, safe committed-prefix replay, and unchanged missing-CSV/date/CLI behavior. Repair only the stale date-detection test fixtures/assertions: partial processor fixtures pass explicit `--date`, complete snapshots are used to test automatic date detection, and incomplete snapshots are expected not to auto-detect. `process_data.py` remains byte-identical. The full pytest suite passes in the aligned local environment. The main agent validates 100,000 rows using the retained laptop CSV before restarting the full import; no dump is downloaded to the development machine.

- [ ] Replace only the pipeline CSV importer and add focused tests.
- [ ] Repair the stale partial-dump date-detection test fixtures/assertions without changing `process_data.py` or its behavior.
- [ ] Run the full repository pytest suite and Python syntax checks.
- [ ] Publish the implementation branch for review and laptop validation; hostings owns the 100,000-row check and restart of the full import.

## Starting state

The worktree is `/Users/ruz/projs/openlibrary-local-db/worktrees/importer-performance`, branch `importer-performance-1`, at commit `49b8bd4b66daad0ea35c938c762c5ac063c92721`, the pinned upstream source. The working tree was clean. The Git remote is `git@github.com:ruz/openlibrary-local-db.git`. `pipeline.py` uses `sqlite-utils.upsert_all` with batch size 5,000 and `alter=True`. No `AGENTS.md`, tags, or `docs/` directory existed at the start. The deployment and retained dataset are managed separately by the hostings repository.

## Changelog

- 2026-10-29: Created the planning record and Cadence documentation indexes on `importer-performance-1`. Recorded benchmark-selected SQLite settings, importer compatibility requirements, and tests for Unit 2. No code changes or real-data downloads were made.
- 2026-10-29: Recorded the untouched pytest baseline (198 passed, 13 failed) and the confirmed stale partial-dump date-detection expectations. Added a bounded test-fixture/assertion repair to Unit 2 while keeping `process_data.py` and processor behavior unchanged.
