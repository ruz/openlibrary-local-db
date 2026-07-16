# OpenLibrary Local DB

![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![Flask](https://img.shields.io/badge/backend-Flask-black.svg)
![SQLite](https://img.shields.io/badge/database-SQLite-003B57.svg)
![Poetry](https://img.shields.io/badge/managed%20with-Poetry-60A5FA.svg)

This project converts the [OpenLibrary](https://openlibrary.org/) data dumps (editions, works, authors) into a single indexed, full-text-searchable SQLite database, and exposes it through a Flask API for ISBN/OL-ID lookups and search.

It consists of:
- **A pipeline** (`pipeline.py` / `download_data.py` / `process_data.py`) that downloads and processes raw OpenLibrary dumps into a compact SQLite database with an ISBN lookup table, indexes, and FTS enabled.
- **An API** (`api/`, Flask) that serves lookups by ISBN or OpenLibrary ID, and paginated full-text search, with HTTP caching (ETag/Last-Modified/Cache-Control).

The official hosted instance of this projects is available at [metadata.booklogr.app](https://metadata.booklogr.app).

## Setup
This project uses [Poetry](https://python-poetry.org/) to manage dependencies and the virtual environment. Install dependencies before running any of the commands below:

```bash
poetry install
```

## Quick Start

`pipeline.py` automates the entire process end-to-end (downloading dumps, processing, importing to SQLite, building the ISBN lookup table, enabling FTS, and optimizing, steps 1-7 below) in one command, and creates/updates your `.env` file so the API is ready to run immediately afterward. There's nothing to download yourself first: `poetry run pipeline all` fetches the dumps automatically, and skips the download step entirely if matching dump files are already present in `data/unprocessed/`.

```bash
poetry run pipeline all
```

Common options:
- `--limit N`: process only N rows per dump file (for a quick smoke test; see "Testing with a smaller sample" below)
- `--input-path`, `--output-path`, `--db`: override the default `./data/unprocessed/`, `./data/processed/`, `test.db` locations
- `--date YYYY-MM-DD`: pin the dump date instead of auto-detecting it (from archive.org for downloads, or from filenames in `--input-path` for processing)
- `--method {auto,torrent,http}`: transport for the download step (default: `auto`, torrent preferred with HTTP fallback)
- `--skip-download`: don't download dump files; use files already present in `--input-path`
- `--skip-env`: don't create/update `.env`

Each stage can also be run independently, useful for re-running just one step:
```bash
poetry run pipeline download   # fetch dumps -> data/unprocessed/
poetry run pipeline process    # dumps -> CSVs
poetry run pipeline import     # CSVs -> SQLite tables
poetry run pipeline index      # isbn_lookup table + indexes
poetry run pipeline fts        # enable full-text search
poetry run pipeline optimize   # optimize the database
```

The manual, step-by-step instructions below describe exactly what the automated pipeline does under the hood, and remain fully supported if you prefer to run them by hand or need finer control.

<details>
<summary><strong>Manual setup (steps 1-7)</strong></summary>

## 1. Prepare the Data
Download the latest `editions`, `works`, and `authors` dumps automatically:

```bash
poetry run pipeline download
```

By default this prefers BitTorrent (faster, and lighter load on OpenLibrary's servers) via the pure-Python [`libtorrent`](https://pypi.org/project/libtorrent/) package (no separate torrent client or binary to install), and automatically falls back to direct HTTP download if BitTorrent isn't available (e.g. no wheel for your platform, network blocks torrent traffic). Force a specific transport with `--method torrent` or `--method http`. Files are placed in `data/unprocessed/`.

> [!TIP]
> You can still download the dumps manually from the [OpenLibrary Developer Portal](https://openlibrary.org/developers/dumps) or [archive.org/details/ol_exports](https://archive.org/details/ol_exports?sort=-publicdate) and place them in `data/unprocessed/` yourself. This remains fully supported.

## 2. Process the Dumps
Run the processing script to clean the data and extract the necessary fields. This script scans the `unprocessed` folder and saves the formatted CSV files into the `processed` folder.

```bash
poetry run python3 process_data.py
```

**Approximate Processed File Sizes:**
- Authors: 800 MB
- Works: 6 GB
- Editions: 13 GB

### Testing with a smaller sample
The full dumps take a long time to process and import, which makes iterating on `process_data.py` or trying out the rest of this guide slow. To work with a smaller sample size instead,

- Limit how many rows are read from the full dump files already in `data/unprocessed/`,
  ```bash
  poetry run python3 process_data.py --limit 5000
  ```

> [!TIP]
> Small samples may not contain rarer data-quality edge cases (e.g. missing author names, `-1` "no image" placeholder IDs, or malformed rows). Use at least a few thousand rows if you want to exercise those cases.

## 3. Import to SQLite
Use [sqlite-utils](https://sqlite-utils.datasette.io/en/stable/) to import the processed CSV files into a new database named `test.db`. Note that the `editions` table is significantly larger than the others and will take the longest to import.

```bash
# Import Authors
sqlite-utils insert test.db authors data/processed/ol_dump_authors_2026-03-31.csv --csv --delimiter=";" --quotechar="|"

# Import Works
sqlite-utils insert test.db works data/processed/ol_dump_works_2026-03-31.csv --csv --delimiter=";" --quotechar="|"

# Import Editions
sqlite-utils insert test.db editions data/processed/ol_dump_editions_2026-03-31.csv --csv --delimiter=";" --quotechar="|"
```

## 4. Build the ISBN Lookup Table
The API's `/v1/edition/<identifier>` endpoint looks up editions by ISBN via a small `isbn_lookup` table (mapping a single ISBN to an `ol_id`), rather than scanning the `isbn_10`/`isbn_13` JSON arrays on every request. Build it by unnesting both ISBN columns:

```bash
sqlite-utils query test.db "
  CREATE TABLE isbn_lookup AS
  SELECT value AS isbn, MIN(ol_id) AS ol_id
  FROM editions, json_each(isbn_10)
  GROUP BY value
  UNION
  SELECT value AS isbn, MIN(ol_id) AS ol_id
  FROM editions, json_each(isbn_13)
  GROUP BY value
"
sqlite-utils create-index test.db isbn_lookup isbn --unique
```

> [!NOTE]
> A small fraction of ISBNs are shared by more than one edition (e.g. simultaneous reprints). `MIN(ol_id)` picks a single, deterministic edition to resolve to in that case.

## 5. Enable Full-Text Search (FTS)
```bash
sqlite-utils enable-fts test.db editions title isbn_10 isbn_13 author_names
```

## 6. Verify and Search via CLI
You can test your database immediately using the `sqlite-utils` command-line interface.

### Search by Title
```bash
sqlite-utils search test.db editions "harry potter and the half-blood prince" --table
```

### Search by ISBN
Since ISBNs are stored as JSON arrays, use SQLite's JSON functions to locate a specific record:
```bash
sqlite-utils query test.db "
  SELECT title, author_names 
  FROM editions, json_each(isbn_13) 
  WHERE json_each.value = '9780545010221'
" --table
```

### Check Table Stats
Verify the total row counts for each table:
```bash
sqlite-utils tables test.db --counts
```

## 7. Optimize database
```bash
sqlite-utils optimize test.db
```

</details>

## Running the API
The backend is a Flask application managed with Poetry.

1.  Navigate to the project root.
2.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
3.  Edit `.env` and set at least `OL_DB` (path to your database file, e.g. `"test.db"`) and `OLDUMP_DATE` (e.g. `"2026-03-31"`). See [Environment variables](#environment-variables) below for the full list of options.

    > [!TIP]
    > If you ran `poetry run pipeline all` (and didn't pass `--skip-env`), `.env` has already been created/updated for you, so skip to step 4.
4.  Install dependencies and start the development server:
    ```bash
    poetry install
    poetry run flask run
    ```

> [!NOTE]
> On first start, the API automatically creates indexes on `editions.ol_id`, `works.ol_id`, and `authors.ol_id` if they don't already exist (`CREATE INDEX IF NOT EXISTS`), so `/v1/edition`, `/v1/work`, and `/v1/author` lookups are fast without a manual step. Building these on a multi-GB database can take a few minutes the first time. If you'd rather pre-build them yourself before starting the API, run:
> ```bash
> sqlite-utils create-index test.db editions ol_id
> sqlite-utils create-index test.db works ol_id
> sqlite-utils create-index test.db authors ol_id
> ```

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `OL_DB` | *(required)* | Path to the SQLite database file to serve (e.g. `test.db`). |
| `OLDUMP_DATE` | *(none)* | Date of the dump the database was built from (e.g. `2026-03-31`); also used by `pipeline.py` when `--date` isn't passed, and reported by the API's `/v1/status` info. |
| `LANDING_PAGE` | *(none)* | Path to an HTML template to render at `/` (e.g. `app/index.html`); if unset, `/` has no landing page. |
| `MAX_SEARCH_LIMIT` | `100` | Maximum number of results allowed per page for `/v1/search`. |
| `CACHE_MAX_AGE` | `3600` | `Cache-Control: max-age` (in seconds) sent with cacheable API responses. |
| `OVERRIDES_DB` | *(none)* | Path to the SQLite file storing [persistent local overrides](#persistent-local-overrides); overrides are entirely disabled until this is set. |
| `EDIT_TOKEN` | *(none)* | Shared secret required (via `X-Edit-Token` header) to list/approve/reject suggestions. |
| `ENABLE_SUGGESTIONS` | `false` | Set to `true`/`1`/`yes` to enable the public, unauthenticated `POST .../suggest` endpoints. |
| `SUGGESTION_RATE_LIMIT` | `5 per hour` | Per-IP rate limit (Flask-Limiter syntax) applied to suggestion submissions. |
| `RATELIMIT_STORAGE_URI` | `memory://` | Backend URI for Flask-Limiter's rate-limit counters; point at a shared store (e.g. Redis) for multi-worker deployments. |
| `FLASK_APP` | *(none)* | Standard Flask entry point, e.g. `api.app` (used by `flask run`). |
| `FLASK_ENV` / `FLASK_DEBUG` | *(none)* | Standard Flask dev-server settings. |

The web frontend (`web/`) reads its own `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | *(required)* | Base URL of the API the frontend talks to (e.g. `http://localhost:5000/`). |

## Updating to a New Dump
OpenLibrary publishes new dumps periodically. To refresh an existing database with one:

1.  Clear out the old dump files so the pipeline fetches the new ones instead of reusing what's on disk:
    ```bash
    rm -f data/unprocessed/ol_dump_*.txt
    ```
    Alternatively, keep the old files and pass `--date YYYY-MM-DD` for the new dump. This forces a download of that date even if older files are still present in `data/unprocessed/`.
2.  Run the pipeline again against the same `--db` you already have:
    ```bash
    poetry run pipeline all
    ```
    Importing is an upsert keyed on `ol_id`, so existing rows are updated and new ones are added in place. Records removed from OpenLibrary since your last import aren't deleted from your database.
3.  If `OVERRIDES_DB` is set, this also runs `pipeline overrides sync` automatically, flagging any override whose upstream value has since changed as `stale`. Resolve those with `pipeline overrides resolve` (see [Persistent Local Overrides](#persistent-local-overrides)).
4.  `.env`'s `OLDUMP_DATE` is updated to match, unless you passed `--skip-env`.

Restart the API afterward to pick up the refreshed database.

## Persistent Local Overrides

Local corrections to a record (fix a typo, add a missing ISBN, etc.) are stored separately from the main database, in a SQLite file set via `OVERRIDES_DB`. They survive the next `pipeline all`/`pipeline import` run and are merged into API responses at read time. If `OVERRIDES_DB` isn't set, this feature is entirely inactive.

Each override remembers the upstream value it was based on. If a later dump changes that value, the override is flagged `stale` instead of silently reapplying.

Changes go through a suggestion queue: anyone can `POST` a suggested correction (or a reversion to upstream data) with no login required, but it only takes effect once approved with `EDIT_TOKEN`. `EDIT_TOKEN` gates moderation (list/approve/reject) only. It does not grant a direct write path. Submissions are also rate-limited per IP and capped in size/volume. The CLI's `pipeline overrides set/...` commands are a separate, direct path for the operator (shell access to the box, not a network-reachable endpoint).

Only a fixed set of fields can be overridden per record type: the CLI's `overrides set` and the API's `POST .../suggest` reject anything else with an error:

| Entity (`pipeline overrides` entity-type / suggest route) | Overridable fields |
| --- | --- |
| `works` (`/v1/work/<ol_id>/suggest`) | `title`, `description`, `authors`, `subjects`, `subject_people`, `subject_places`, `covers`, `series` |
| `authors` (`/v1/author/<ol_id>/suggest`) | `name`, `birth_date`, `death_date`, `bio`, `alternate_names`, `photos` |
| `editions` (`/v1/edition/<identifier>/suggest`) | `title`, `subtitle`, `publish_date`, `publish_year`, `number_of_pages`, `physical_format`, `publishers`, `isbn_10`, `isbn_13`, `subjects`, `languages`, `authors`, `author_names`, `works` |

> [!NOTE]
> `ol_id` itself can never be overridden. Fields that are JSON arrays in the database (`authors`, `subjects`, `isbn_10`, `covers`, etc.) expect a JSON-encoded value when set through the API; the CLI's `--field KEY=VALUE` treats every value as a plain string, so it's best suited to scalar fields like `title`, `name`, or `publish_date`.

### Managing overrides via the CLI
Set `OVERRIDES_DB` in `.env` (loaded automatically) or pass `--overrides-db` to every command below:
```bash
# Correct a field on an imported record
poetry run pipeline overrides set works OL27448W --field title="Corrected Title" --note "typo fix"

# List what's stored
poetry run pipeline overrides list

# List, approve, or reject pending suggestions from the public suggestion queue
poetry run pipeline overrides suggestions list --status pending
poetry run pipeline overrides suggestions approve 42
poetry run pipeline overrides suggestions reject 42

# After re-running the pipeline against a newer dump, check for upstream drift
poetry run pipeline overrides sync

# Reconcile a stale override: keep your edit, defer to OpenLibrary's new value, or drop it
poetry run pipeline overrides resolve works OL27448W --keep-mine
poetry run pipeline overrides resolve works OL27448W --accept-upstream
poetry run pipeline overrides resolve works OL27448W --discard

# Export active overrides for manual submission on openlibrary.org
poetry run pipeline overrides export --output my_corrections.json
poetry run pipeline overrides mark-submitted works OL27448W

# Wipe every stored override (explicit, never automatic)
poetry run pipeline overrides clear --yes
```

`pipeline overrides sync` also runs automatically at the end of `pipeline all`. It's a no-op if `OVERRIDES_DB` isn't set.

`export` produces a JSON file (OL key + patched fields) for manual submission on openlibrary.org. There's no automated submission, since that requires your own OpenLibrary account.

### Suggesting an edit via the API
Set `ENABLE_SUGGESTIONS=true` in `.env` (unset by default, so the routes below 404 until you do). No login required:
```bash
# Propose a field correction
curl -X POST http://localhost:5000/v1/work/OL27448W/suggest \
  -H "Content-Type: application/json" \
  -d '{"action": "patch", "patch": {"title": "Corrected Title"}, "note": "typo fix"}'

# Propose reverting a record to plain OpenLibrary data (undoing whatever override currently applies)
curl -X POST http://localhost:5000/v1/work/OL27448W/suggest \
  -H "Content-Type: application/json" \
  -d '{"action": "delete", "note": "this correction is no longer accurate"}'
```
The same `POST .../suggest` route exists for `/v1/author/<ol_id>` and `/v1/edition/<identifier>` (identifier may be an OL id or ISBN). A successful submission returns `201` with `{"id": ..., "status": "pending"}` and does not affect what `GET` returns until approved.

Submissions are throttled by `SUGGESTION_RATE_LIMIT` (default `5 per hour` per IP, via [Flask-Limiter](https://flask-limiter.readthedocs.io/)) and capped in size and volume (oversized patches/notes, or too many pending suggestions on one record, are rejected with `400`/`429`).

### Moderating suggestions (requires `EDIT_TOKEN`)
```bash
# List pending suggestions
curl http://localhost:5000/v1/suggestions?status=pending -H "X-Edit-Token: your-token"
# or: poetry run pipeline overrides suggestions list --status pending

# Approve one -- promotes it into a real override (or discards one, for a "delete" suggestion)
curl -X POST http://localhost:5000/v1/suggestions/42/approve -H "X-Edit-Token: your-token"
# or: poetry run pipeline overrides suggestions approve 42

# Reject one -- it's kept (for audit) but never affects served data
curl -X POST http://localhost:5000/v1/suggestions/42/reject -H "X-Edit-Token: your-token"
# or: poetry run pipeline overrides suggestions reject 42
```
`GET` requests to `/v1/work`, `/v1/author`, `/v1/edition` transparently merge any *approved* override into the response (adding an `_override_status` field when one applies). Pending or rejected suggestions never do.

> [!NOTE]
> Search (`/v1/search`) still matches against the original, un-overridden text. An edited title won't be *findable* by its new wording until a future dump re-indexes it. Overridden fields are still merged into individual result rows, though.

## Running Tests
The `api/` Flask app, `process_data.py`, and `pipeline.py` have a pytest suite under `tests/`. It builds its own small SQLite fixture database, so it doesn't require a real OpenLibrary dump or `test.db` to be present.

```bash
poetry install
poetry run pytest tests/ -v
```

## Running the Web Interface
The frontend is a React application located in the `web` directory. It's intended for demonstrative purposes only (e.g. exercising lookups/search and the moderation flow by hand), not a production-ready UI.

1.  Navigate to the `web` directory.
2.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
3.  Edit `.env` and configure `VITE_API_URL`. By default, `http://localhost:5000/` should work for local development.
4.  Install dependencies and start the development server:
    ```bash
    npm install
    npm run dev
    ```