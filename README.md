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

## 4. Enable Full-Text Search (FTS)
```bash
sqlite-utils enable-fts test.db editions title isbn_10 isbn_13 author_names
```

## 5. Verify and Search via CLI
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

## 6. Optimize database
```bash
sqlite-utils optimize test.db
```

## 7. Running the API
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

## 8. Running the Web Interface
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