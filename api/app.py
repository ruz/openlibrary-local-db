from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import sqlite3
from dotenv import load_dotenv
import os
from flasgger import Swagger
import json
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app)

landing_page = os.getenv("LANDING_PAGE")
if landing_page:
    app.template_folder = os.path.dirname(os.path.abspath(landing_page))

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def parse_json_fields(row, fields):
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            try:
                row[field] = json.loads(value)
            except json.JSONDecodeError:
                row[field] = []
    return row

SEARCH_JSON_FIELDS = ("author_names", "languages", "isbn_13", "isbn_10")
EDITION_JSON_FIELDS = ("publishers", "isbn_10", "isbn_13", "subjects", "languages", "authors", "author_names", "works")
WORK_JSON_FIELDS = ("authors", "subjects", "subject_people", "subject_places", "covers", "series")
AUTHOR_JSON_FIELDS = ("alternate_names", "photos")

MAX_SEARCH_LIMIT = int(os.getenv("MAX_SEARCH_LIMIT", 100))
CACHE_MAX_AGE = int(os.getenv("CACHE_MAX_AGE", 3600))

def get_db_cache_metadata():
    """
    The DB is a static dump that only changes when an operator re-imports it,
    so its mtime/size make a cheap, self-invalidating cache key (os.stat is
    a fast syscall, safe to call per-request).
    """
    try:
        stat = os.stat(os.getenv("OL_DB"))
    except OSError:
        return None, None
    return stat.st_mtime, f"{int(stat.st_mtime)}-{stat.st_size}"

def cache_headers(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        if response.status_code == 200:
            last_modified, etag = get_db_cache_metadata()
            if last_modified is not None:
                response.last_modified = last_modified
                response.set_etag(etag)
                response.cache_control.public = True
                response.cache_control.max_age = CACHE_MAX_AGE
                response = response.make_conditional(request)
        return response
    return wrapped

app.config['SWAGGER'] = {
  "openapi": "3.0.0",
  "info": {
    "title": "openlibrary-local-db API",
    "description": "API for accessing a dumped version of OpenLibrary",
    "contact": {
      "responsibleDeveloper": "Andreas Backström",
      "url": "https://github.com/mozzo1000/openlibrary-local-db",
    },
    "version": "1.0.0"
  },
    "specs_route": "/api/docs"
}
swagger = Swagger(app)


def get_db_connection():
    conn = sqlite3.connect(os.getenv("OL_DB"), check_same_thread=False)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA mmap_size=31000000000;")
    conn.execute("PRAGMA cache_size=-2000000;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    for table, column in (("editions", "ol_id"), ("works", "ol_id"), ("authors", "ol_id")):
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ol_id ON {table}({column})")
        except sqlite3.OperationalError as e:
            app.logger.warning(f"Could not ensure index on {table}.{column}: {e}")

    return conn

con = get_db_connection()

@app.errorhandler(sqlite3.OperationalError)
def handle_db_error(e):
    return jsonify({"error": str(e)}), 400

@app.route("/v1/search/<query>")
@cache_headers
def search(query):
    """
    Search books with advanced filtering and sorting
    ---
    parameters:
      - name: query
        in: path
        type: string
        required: true
      - name: limit
        in: query
        type: integer
        default: 10
        description: Maximum number of results to return (capped at 100).
      - name: offset
        in: query
        type: integer
        default: 0
        description: Number of results to skip, for pagination.
      - name: lang
        in: query
        type: string
        description: Language code (e.g., 'eng')
      - name: sort
        in: query
        type: string
        enum: [relevance, newest, oldest]
        default: relevance
    responses:
      200:
        description: >
          Object with `results` (array of editions), `limit`, `offset`,
          and `has_more` (whether another page is available).
      404:
        description: No results found for the first page of this query.
    """

    limit = request.args.get("limit", default=10, type=int)
    if not limit or limit < 1:
        limit = 10
    limit = min(limit, MAX_SEARCH_LIMIT)

    offset = request.args.get("offset", default=0, type=int)
    if not offset or offset < 0:
        offset = 0

    lang = request.args.get("lang", type=str)
    sort_mode = request.args.get("sort", default="relevance", type=str)

    words = query.split()
    safe_query = " AND ".join([f'"{word.replace('"', '""')}"' for word in words if word])

    base_sql = """
        SELECT e.title, e.isbn_10, e.isbn_13, e.publish_date, e.author_names, e.languages
        FROM editions e
        JOIN editions_fts f ON e.rowid = f.rowid
        WHERE f.editions_fts MATCH ?
    """

    base_sql += " AND (e.isbn_10 != '[]' OR e.isbn_13 != '[]')"

    params = [safe_query]

    if lang:
        base_sql += " AND EXISTS (SELECT 1 FROM json_each(e.languages) WHERE value = ?)"
        params.append(lang)

    if sort_mode == "newest":
        base_sql += " ORDER BY e.publish_year DESC, e.rowid"
    elif sort_mode == "oldest":
        # Push year 0 (missing) to the bottom
        base_sql += " ORDER BY e.publish_year = 0, e.publish_year ASC, e.rowid"
    else:
        base_sql += """
            ORDER BY (
                f.rank - (CASE WHEN json_array_length(e.author_names) > 0 THEN 0.5 ELSE 0 END)
            ) DESC, e.rowid
        """

    base_sql += " LIMIT ? OFFSET ?"
    params.append(limit + 1)
    params.append(offset)

    cur = con.cursor()
    results = cur.execute(base_sql, params).fetchall()

    has_more = len(results) > limit
    results = results[:limit]

    if results:
        for row in results:
            parse_json_fields(row, SEARCH_JSON_FIELDS)
    elif offset == 0:
        return jsonify({"message": "Not found"}), 404

    return jsonify({
        "results": results,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    })


@app.route("/v1/edition/<identifier>")
@cache_headers
def get_edition(identifier):
    """
    Get full details of a specific edition by OLID, ISBN-10, or ISBN-13.
    Optimized to achieve sub-millisecond execution over 49M rows.
    ---
    parameters:
      - name: identifier
        in: path
        type: string
        required: true
        description: The Open Library ID (e.g., OL27348000M) or an ISBN string.
    responses:
      200:
        description: Edition details found.
      404:
        description: Edition not found.
    """
    cur = con.cursor()

    target_ol_id = None

    if identifier.startswith("OL"):
        target_ol_id = identifier
    else:
        # It's an ISBN. Query ONLY the small lookup table.
        # This uses the B-Tree index on 'isbn' instantly.
        row = cur.execute(
            "SELECT ol_id FROM isbn_lookup WHERE isbn = ? LIMIT 1", 
            (identifier,)
        ).fetchone()
        
        if row:
            # Handle both tuple and dict row-factory outputs safely
            target_ol_id = row["ol_id"] if isinstance(row, dict) else row[0]
        else:
            # If it's not found in the index, we stop immediately. 
            # Total time elapsed: <1ms. No full table scan!
            return jsonify({"message": f"Edition {identifier} not found"}), 404

    sql = """
        SELECT 
            ol_id, title, subtitle, publish_date, publish_year,
            number_of_pages, physical_format,
            publishers,
            isbn_10,
            isbn_13,
            subjects,
            languages,
            authors,
            author_names,
            works
        FROM editions
        WHERE ol_id = ?
        LIMIT 1
    """
    result = cur.execute(sql, (target_ol_id,)).fetchone()
    if result:
        parse_json_fields(result, EDITION_JSON_FIELDS)
        return jsonify(result)

    return jsonify({"message": f"Edition {identifier} not found"}), 404

@app.route("/v1/work/<ol_id>")
@cache_headers
def get_work(ol_id):
    """
    Get full details of a work by OLID
    ---
    parameters:
      - name: ol_id
        in: path
        type: string
        required: true
        description: The Open Library Work ID (e.g., OL17352669W)
    """
    sql = """
        SELECT
            ol_id, title, description,
            authors, subjects, subject_people, subject_places, covers, series
        FROM works
        WHERE ol_id = ?
        LIMIT 1
    """
    cur = con.cursor()

    # Strip the prefix if the user includes it by accident
    clean_id = ol_id.replace("/works/", "")
    result = cur.execute(sql, (clean_id,)).fetchone()

    if result:
        parse_json_fields(result, WORK_JSON_FIELDS)
        return jsonify(result)
    return jsonify({"message": f"Work {ol_id} not found"}), 404


@app.route("/v1/author/<ol_id>")
@cache_headers
def get_author(ol_id):
    """
    Get full details of an author by OLID
    ---
    parameters:
      - name: ol_id
        in: path
        type: string
        required: true
        description: The Open Library Author ID (e.g., OL7115219A)
    """
    sql = """
        SELECT
            ol_id, name, birth_date, death_date, bio,
            alternate_names, photos
        FROM authors
        WHERE ol_id = ?
        LIMIT 1
    """
    cur = con.cursor()

    # Strip the prefix if the user includes it by accident
    clean_id = ol_id.replace("/authors/", "")
    result = cur.execute(sql, (clean_id,)).fetchone()

    if result:
        parse_json_fields(result, AUTHOR_JSON_FIELDS)
        return jsonify(result)
    return jsonify({"message": f"Author {ol_id} not found"}), 404

@app.route("/v1/info")
def info():
    """
    Get API version and OpenLibrary dump metadata
    ---
    responses:
      200:
        description: API and dump info.
    """
    return {
        "name": "openlibrary-local-db-api",
        "version": "1.0.0",
        "docs": request.host_url + "api/docs",
        "oldump_date": os.getenv("OLDUMP_DATE")
    }

@app.route("/")
def index():
    if landing_page:
        template_file = os.path.basename(landing_page)
        try:
            return render_template(template_file)
        except Exception as e:
            app.logger.warning(f"Failed to render landing page: {e}")
    return info()