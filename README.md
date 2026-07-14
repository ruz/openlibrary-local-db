# Database Setup and Installation Guide

## 1. Prepare the Data
Download the latest `editions`, `works`, and `authors` dumps from the [OpenLibrary Developer Portal](https://openlibrary.org/developers/dumps). Place the raw files into the following directory:

`data/unprocessed/`

> [!TIP]
>For faster downloads you can use the torrents available at [archive.org/details/ol_exports](https://archive.org/details/ol_exports?sort=-publicdate). Ensure you select the latest ol_dump file (e.g., ol_dump_2026-04-30), not the ol_cdump version.

## 2. Process the Dumps
Run the processing script to clean the data and extract the necessary fields. This script scans the `unprocessed` folder and saves the formatted CSV files into the `processed` folder.

```bash
python3 process_data.py
```

**Approximate Processed File Sizes:**
- Authors: 800 MB
- Works: 6 GB
- Editions: 13 GB

### Testing with a smaller sample
The full dumps take a long time to process and import, which makes iterating on `process_data.py` or trying out the rest of this guide slow. To work with a smaller sample size instead,

- Limit how many rows are read from the full dump files already in `data/unprocessed/`,
  ```bash
  python3 process_data.py --limit 5000
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

## 8. Running the API
The backend is a Flask application managed with Poetry.

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

## 9. Running the Web Interface
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