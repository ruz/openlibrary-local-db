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

## Quick Start: Automated Pipeline

`pipeline.py` automates the entire process end-to-end (downloading dumps, processing, importing to SQLite, building the ISBN lookup table, enabling FTS, and optimizing — steps 1-7 below) in one command, and creates/updates your `.env` file so the API is ready to run immediately afterward. You don't need to download anything yourself first — `poetry run pipeline all` downloads the dumps automatically, and skips the download step entirely if matching dump files are already present in `data/unprocessed/`.

```bash
poetry run pipeline all
```

Common options:
- `--limit N` — process only N rows per dump file (for a quick smoke test; see "Testing with a smaller sample" below)
- `--input-path`, `--output-path`, `--db` — override the default `./data/unprocessed/`, `./data/processed/`, `test.db` locations
- `--date YYYY-MM-DD` — pin the dump date instead of auto-detecting it (from archive.org for downloads, or from filenames in `--input-path` for processing)
- `--method {auto,torrent,http}` — transport for the download step (default: `auto`, torrent preferred with HTTP fallback)
- `--skip-download` — don't download dump files; use files already present in `--input-path`
- `--skip-env` — don't create/update `.env`

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

By default this prefers BitTorrent (faster, and lighter load on OpenLibrary's servers) via the pure-Python [`libtorrent`](https://pypi.org/project/libtorrent/) package — no separate torrent client or binary to install — and automatically falls back to direct HTTP download if BitTorrent isn't available (e.g. no wheel for your platform, network blocks torrent traffic). Force a specific transport with `--method torrent` or `--method http`. Files are placed in `data/unprocessed/`.

> [!TIP]
> You can still download the dumps manually from the [OpenLibrary Developer Portal](https://openlibrary.org/developers/dumps) or [archive.org/details/ol_exports](https://archive.org/details/ol_exports?sort=-publicdate) and place them in `data/unprocessed/` yourself — this remains fully supported.

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

## 8. Running the API
The backend is a Flask application managed with Poetry.

> [!NOTE]
> On first start, the API automatically creates indexes on `editions.ol_id`, `works.ol_id`, and `authors.ol_id` if they don't already exist (`CREATE INDEX IF NOT EXISTS`), so `/v1/edition`, `/v1/work`, and `/v1/author` lookups are fast without a manual step. Building these on a multi-GB database can take a few minutes the first time. If you'd rather pre-build them yourself before starting the API, run:
> ```bash
> sqlite-utils create-index test.db editions ol_id
> sqlite-utils create-index test.db works ol_id
> sqlite-utils create-index test.db authors ol_id
> ```

> [!TIP]
> If you ran `poetry run pipeline all` (and didn't pass `--skip-env`), `.env` has already been created/updated with `OL_DB` and `OLDUMP_DATE` — you can skip steps 1-3 below.

1.  Navigate to the project root.
2.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
3.  Edit `.env` and configure the following variables:
    *   `OL_DB`: The path to your database file (e.g., `"test.db"`).
    *   `OLDUMP_DATE`: The date associated with your specific dump files (e.g., `"2026-03-31"`).
4.  Install dependencies and start the development server:
    ```bash
    poetry install
    poetry run flask run
    ```

## 9. Running Tests
The `api/` Flask app, `process_data.py`, and `pipeline.py` have a pytest suite under `tests/`. It builds its own small SQLite fixture database, so it doesn't require a real OpenLibrary dump or `test.db` to be present.

```bash
poetry install
poetry run pytest tests/ -v
```

## 10. Running the Web Interface
The frontend is a React application located in the `web` directory.

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