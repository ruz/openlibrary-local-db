from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
from dotenv import load_dotenv
import os
import hashlib
from flasgger import Swagger
import json
from functools import wraps

import overrides

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

# Patchable columns per entity (everything selectable except the ol_id key itself).
EDITION_PATCHABLE_FIELDS = (
    "title", "subtitle", "publish_date", "publish_year", "number_of_pages", "physical_format",
    "publishers", "isbn_10", "isbn_13", "subjects", "languages", "authors", "author_names", "works",
)
WORK_PATCHABLE_FIELDS = (
    "title", "description", "authors", "subjects", "subject_people", "subject_places", "covers", "series",
)
AUTHOR_PATCHABLE_FIELDS = ("name", "birth_date", "death_date", "bio", "alternate_names", "photos")

MAX_SEARCH_LIMIT = int(os.getenv("MAX_SEARCH_LIMIT", 100))
CACHE_MAX_AGE = int(os.getenv("CACHE_MAX_AGE", 3600))

EDIT_TOKEN = os.getenv("EDIT_TOKEN")
ENABLE_SUGGESTIONS = os.getenv("ENABLE_SUGGESTIONS", "").lower() in ("1", "true", "yes")
SUGGESTION_RATE_LIMIT = os.getenv("SUGGESTION_RATE_LIMIT", "5 per hour")
overrides_con = overrides.get_overrides_db()

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    default_limits=[],
)


def require_edit_token(view):
    """Gates the moderation surface (list/approve/reject suggestions) only --
    there is no longer a direct trusted-write path over HTTP; every change
    goes through the suggestion queue."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not EDIT_TOKEN or request.headers.get("X-Edit-Token") != EDIT_TOKEN:
            return jsonify({"message": "Not found"}), 404
        if overrides_con is None:
            return jsonify({"error": "OVERRIDES_DB is not configured"}), 503
        return view(*args, **kwargs)
    return wrapped


def require_suggestions_enabled(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not ENABLE_SUGGESTIONS or overrides_con is None:
            return jsonify({"message": "Not found"}), 404
        return view(*args, **kwargs)
    return wrapped


def apply_override(result, entity_type, ol_id):
    """Merge a stored override onto an API result dict, in place. No-op if
    the overrides feature is disabled or no override exists for this record."""
    if overrides_con is None:
        return result
    row = overrides.get_override(overrides_con, entity_type, ol_id)
    if row is None:
        return result
    result.update(json.loads(row["patch"]))
    result["_override_status"] = row["status"]
    return result


ENTITY_JSON_FIELDS = {"editions": EDITION_JSON_FIELDS, "works": WORK_JSON_FIELDS, "authors": AUTHOR_JSON_FIELDS}


def _paginate_params():
    """Shared limit/offset parsing + clamping, used by search and the browse
    (list) endpoints."""
    limit = request.args.get("limit", default=10, type=int)
    if not limit or limit < 1:
        limit = 10
    limit = min(limit, MAX_SEARCH_LIMIT)

    offset = request.args.get("offset", default=0, type=int)
    if not offset or offset < 0:
        offset = 0

    return limit, offset


def _submitter_hash():
    return hashlib.sha256((request.remote_addr or "").encode()).hexdigest()


def _create_entity_suggestion(entity_type, ol_id, patchable_fields):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    action = body.get("action", "patch")
    patch = body.get("patch") or {}
    note = body.get("note")

    if action == "patch":
        if not isinstance(patch, dict) or not patch:
            return jsonify({"error": "'patch' suggestions require a non-empty 'patch' object"}), 400
        unknown = set(patch) - set(patchable_fields)
        if unknown:
            return jsonify({"error": f"Unknown field(s): {sorted(unknown)}"}), 400
    elif action == "delete":
        patch = {}
    else:
        return jsonify({"error": f"Unknown action: {action!r}"}), 400

    cur = con.cursor()
    base_row = cur.execute(f"SELECT 1 FROM {entity_type} WHERE ol_id = ?", (ol_id,)).fetchone()
    if base_row is None:
        return jsonify({"message": f"{ol_id} not found"}), 404

    try:
        suggestion = overrides.create_suggestion(
            overrides_con, entity_type, ol_id, action, patch, note, _submitter_hash()
        )
    except overrides.SuggestionError as e:
        return jsonify({"error": str(e)}), e.status_code

    return jsonify({"id": suggestion["id"], "status": suggestion["status"]}), 201

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
    "specs_route": "/api/docs",
    "tags": [
        {"name": "Search", "description": "Full-text search over editions."},
        {"name": "Editions", "description": "Lookup and suggest corrections for editions."},
        {"name": "Works", "description": "Lookup and suggest corrections for works."},
        {"name": "Authors", "description": "Lookup and suggest corrections for authors."},
        {"name": "Moderation", "description": "Review and manage the suggestion queue. Requires X-Edit-Token."},
        {"name": "Info", "description": "API and dump metadata."},
    ],
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
    tags:
      - Search
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

    limit, offset = _paginate_params()

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


def resolve_edition_ol_id(identifier):
    """Resolve an edition identifier (OL id or ISBN) to a canonical ol_id, or
    None if it can't be resolved (caller returns 404)."""
    if identifier.startswith("OL"):
        return identifier

    # It's an ISBN. Query ONLY the small lookup table.
    # This uses the B-Tree index on 'isbn' instantly.
    cur = con.cursor()
    row = cur.execute(
        "SELECT ol_id FROM isbn_lookup WHERE isbn = ? LIMIT 1",
        (identifier,)
    ).fetchone()
    if row:
        # Handle both tuple and dict row-factory outputs safely
        return row["ol_id"] if isinstance(row, dict) else row[0]
    return None


@app.route("/v1/editions")
@cache_headers
def list_editions():
    """
    Browse editions with filtering, sorting, and pagination.
    ---
    tags:
      - Editions
    parameters:
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
      - name: format
        in: query
        type: string
        description: Exact physical format (e.g., 'Hardcover')
      - name: year_min
        in: query
        type: integer
        description: Only include editions published in or after this year.
      - name: year_max
        in: query
        type: integer
        description: Only include editions published in or before this year.
      - name: title
        in: query
        type: string
        description: Case-insensitive title prefix filter.
      - name: sort
        in: query
        type: string
        enum: [title, title_desc, newest, oldest]
        default: title
    responses:
      200:
        description: >
          Object with `results` (array of editions), `limit`, `offset`,
          and `has_more` (whether another page is available).
    """
    limit, offset = _paginate_params()

    lang = request.args.get("lang", type=str)
    fmt = request.args.get("format", type=str)
    year_min = request.args.get("year_min", type=int)
    year_max = request.args.get("year_max", type=int)
    title = request.args.get("title", type=str)
    sort_mode = request.args.get("sort", default="title", type=str)

    base_sql = """
        SELECT ol_id, title, subtitle, publish_date, publish_year, physical_format,
               isbn_10, isbn_13, languages, author_names, works
        FROM editions
        WHERE 1=1
    """
    params = []

    if lang:
        base_sql += " AND EXISTS (SELECT 1 FROM json_each(languages) WHERE value = ?)"
        params.append(lang)
    if fmt:
        base_sql += " AND physical_format = ?"
        params.append(fmt)
    if year_min is not None:
        base_sql += " AND publish_year >= ?"
        params.append(year_min)
    if year_max is not None:
        base_sql += " AND publish_year <= ?"
        params.append(year_max)
    if title:
        base_sql += " AND title LIKE ? COLLATE NOCASE"
        params.append(f"{title}%")

    if sort_mode == "newest":
        base_sql += " ORDER BY publish_year DESC, rowid"
    elif sort_mode == "oldest":
        base_sql += " ORDER BY publish_year = 0, publish_year ASC, rowid"
    elif sort_mode == "title_desc":
        base_sql += " ORDER BY title COLLATE NOCASE DESC, rowid"
    else:
        base_sql += " ORDER BY title COLLATE NOCASE ASC, rowid"

    base_sql += " LIMIT ? OFFSET ?"
    params.append(limit + 1)
    params.append(offset)

    cur = con.cursor()
    results = cur.execute(base_sql, params).fetchall()

    has_more = len(results) > limit
    results = results[:limit]

    for row in results:
        parse_json_fields(row, EDITION_JSON_FIELDS)
        apply_override(row, "editions", row["ol_id"])

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
    tags:
      - Editions
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

    target_ol_id = resolve_edition_ol_id(identifier)
    if target_ol_id is None:
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
        apply_override(result, "editions", target_ol_id)
        return jsonify(result)

    return jsonify({"message": f"Edition {identifier} not found"}), 404


@app.route("/v1/edition/<identifier>/suggest", methods=["POST"])
@require_suggestions_enabled
@limiter.limit(SUGGESTION_RATE_LIMIT)
def suggest_edition(identifier):
    """
    Suggest a correction (or a reversion to upstream data) for an edition.
    No authentication required; rate limited. Suggestions are queued for
    operator review and never affect served data until approved.
    ---
    tags:
      - Editions
    parameters:
      - name: identifier
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          description: >
            {"action": "patch", "patch": {field: value, ...}, "note": "..."} to
            propose field changes, or {"action": "delete", "note": "..."} to
            propose reverting the record to plain upstream data.
    responses:
      201:
        description: Suggestion queued for review.
      400:
        description: Unknown field(s), bad action, or oversized payload.
      404:
        description: Edition not found, or suggestions are not enabled.
      429:
        description: Rate limited, or too many pending suggestions for this record.
    """
    target_ol_id = resolve_edition_ol_id(identifier)
    if target_ol_id is None:
        return jsonify({"message": f"Edition {identifier} not found"}), 404
    return _create_entity_suggestion("editions", target_ol_id, EDITION_PATCHABLE_FIELDS)


@app.route("/v1/works")
@cache_headers
def list_works():
    """
    Browse works with filtering, sorting, and pagination.
    ---
    tags:
      - Works
    parameters:
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
      - name: subject
        in: query
        type: string
        description: Exact subject match (e.g., 'Fiction')
      - name: title
        in: query
        type: string
        description: Case-insensitive title prefix filter.
      - name: sort
        in: query
        type: string
        enum: [title, title_desc]
        default: title
    responses:
      200:
        description: >
          Object with `results` (array of works), `limit`, `offset`,
          and `has_more` (whether another page is available).
    """
    limit, offset = _paginate_params()

    subject = request.args.get("subject", type=str)
    title = request.args.get("title", type=str)
    sort_mode = request.args.get("sort", default="title", type=str)

    base_sql = """
        SELECT ol_id, title, description, authors, subjects, covers
        FROM works
        WHERE 1=1
    """
    params = []

    if subject:
        base_sql += " AND EXISTS (SELECT 1 FROM json_each(subjects) WHERE value = ?)"
        params.append(subject)
    if title:
        base_sql += " AND title LIKE ? COLLATE NOCASE"
        params.append(f"{title}%")

    if sort_mode == "title_desc":
        base_sql += " ORDER BY title COLLATE NOCASE DESC, rowid"
    else:
        base_sql += " ORDER BY title COLLATE NOCASE ASC, rowid"

    base_sql += " LIMIT ? OFFSET ?"
    params.append(limit + 1)
    params.append(offset)

    cur = con.cursor()
    results = cur.execute(base_sql, params).fetchall()

    has_more = len(results) > limit
    results = results[:limit]

    for row in results:
        parse_json_fields(row, WORK_JSON_FIELDS)
        apply_override(row, "works", row["ol_id"])

    return jsonify({
        "results": results,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    })


@app.route("/v1/work/<ol_id>")
@cache_headers
def get_work(ol_id):
    """
    Get full details of a work by OLID
    ---
    tags:
      - Works
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
        apply_override(result, "works", clean_id)
        return jsonify(result)
    return jsonify({"message": f"Work {ol_id} not found"}), 404


@app.route("/v1/work/<ol_id>/suggest", methods=["POST"])
@require_suggestions_enabled
@limiter.limit(SUGGESTION_RATE_LIMIT)
def suggest_work(ol_id):
    """
    Suggest a correction (or a reversion to upstream data) for a work.
    No authentication required; rate limited. Suggestions are queued for
    operator review and never affect served data until approved.
    ---
    tags:
      - Works
    parameters:
      - name: ol_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          description: >
            {"action": "patch", "patch": {field: value, ...}, "note": "..."} to
            propose field changes, or {"action": "delete", "note": "..."} to
            propose reverting the record to plain upstream data.
    responses:
      201:
        description: Suggestion queued for review.
      400:
        description: Unknown field(s), bad action, or oversized payload.
      404:
        description: Work not found, or suggestions are not enabled.
      429:
        description: Rate limited, or too many pending suggestions for this record.
    """
    clean_id = ol_id.replace("/works/", "")
    return _create_entity_suggestion("works", clean_id, WORK_PATCHABLE_FIELDS)


@app.route("/v1/authors")
@cache_headers
def list_authors():
    """
    Browse authors with filtering, sorting, and pagination.
    ---
    tags:
      - Authors
    parameters:
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
      - name: name
        in: query
        type: string
        description: Case-insensitive name prefix filter.
      - name: sort
        in: query
        type: string
        enum: [name, name_desc]
        default: name
    responses:
      200:
        description: >
          Object with `results` (array of authors), `limit`, `offset`,
          and `has_more` (whether another page is available).
    """
    limit, offset = _paginate_params()

    name = request.args.get("name", type=str)
    sort_mode = request.args.get("sort", default="name", type=str)

    base_sql = """
        SELECT ol_id, name, birth_date, death_date, photos
        FROM authors
        WHERE 1=1
    """
    params = []

    if name:
        base_sql += " AND name LIKE ? COLLATE NOCASE"
        params.append(f"{name}%")

    if sort_mode == "name_desc":
        base_sql += " ORDER BY name COLLATE NOCASE DESC, rowid"
    else:
        base_sql += " ORDER BY name COLLATE NOCASE ASC, rowid"

    base_sql += " LIMIT ? OFFSET ?"
    params.append(limit + 1)
    params.append(offset)

    cur = con.cursor()
    results = cur.execute(base_sql, params).fetchall()

    has_more = len(results) > limit
    results = results[:limit]

    for row in results:
        parse_json_fields(row, AUTHOR_JSON_FIELDS)
        apply_override(row, "authors", row["ol_id"])

    return jsonify({
        "results": results,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    })


@app.route("/v1/author/<ol_id>")
@cache_headers
def get_author(ol_id):
    """
    Get full details of an author by OLID
    ---
    tags:
      - Authors
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
        apply_override(result, "authors", clean_id)
        return jsonify(result)
    return jsonify({"message": f"Author {ol_id} not found"}), 404


@app.route("/v1/author/<ol_id>/suggest", methods=["POST"])
@require_suggestions_enabled
@limiter.limit(SUGGESTION_RATE_LIMIT)
def suggest_author(ol_id):
    """
    Suggest a correction (or a reversion to upstream data) for an author.
    No authentication required; rate limited. Suggestions are queued for
    operator review and never affect served data until approved.
    ---
    tags:
      - Authors
    parameters:
      - name: ol_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          description: >
            {"action": "patch", "patch": {field: value, ...}, "note": "..."} to
            propose field changes, or {"action": "delete", "note": "..."} to
            propose reverting the record to plain upstream data.
    responses:
      201:
        description: Suggestion queued for review.
      400:
        description: Unknown field(s), bad action, or oversized payload.
      404:
        description: Author not found, or suggestions are not enabled.
      429:
        description: Rate limited, or too many pending suggestions for this record.
    """
    clean_id = ol_id.replace("/authors/", "")
    return _create_entity_suggestion("authors", clean_id, AUTHOR_PATCHABLE_FIELDS)


@app.route("/v1/suggestions")
@require_edit_token
def list_suggestions_route():
    """
    List stored suggestions (moderation surface). Requires X-Edit-Token.
    ---
    tags:
      - Moderation
    parameters:
      - name: status
        in: query
        type: string
        enum: [pending, approved, rejected]
      - name: entity_type
        in: query
        type: string
        enum: [authors, works, editions]
    responses:
      200:
        description: List of suggestions.
    """
    status = request.args.get("status")
    entity_type = request.args.get("entity_type")
    rows = overrides.list_suggestions(overrides_con, status=status, entity_type=entity_type)
    for row in rows:
        row["patch"] = json.loads(row["patch"])
    return jsonify({"suggestions": rows})


@app.route("/v1/suggestions/<int:suggestion_id>/approve", methods=["POST"])
@require_edit_token
def approve_suggestion_route(suggestion_id):
    """
    Approve a pending suggestion, promoting it into a real override.
    Requires X-Edit-Token.
    ---
    tags:
      - Moderation
    parameters:
      - name: suggestion_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Suggestion approved.
      404:
        description: No pending suggestion with this id.
    """
    suggestion = overrides.get_suggestion(overrides_con, suggestion_id)
    if suggestion is None or suggestion["status"] != "pending":
        return jsonify({"message": "No pending suggestion found"}), 404

    base_row = None
    if suggestion["action"] == "patch":
        cur = con.cursor()
        base_row = cur.execute(
            f"SELECT * FROM {suggestion['entity_type']} WHERE ol_id = ?", (suggestion["ol_id"],)
        ).fetchone()
        if base_row is None:
            return jsonify({"message": f"{suggestion['ol_id']} no longer exists in the base DB"}), 404

    dump_date = os.getenv("OLDUMP_DATE") or ""
    result = overrides.approve_suggestion(overrides_con, suggestion_id, base_row, dump_date)
    result["patch"] = json.loads(result["patch"])
    return jsonify(result)


@app.route("/v1/suggestions/<int:suggestion_id>/reject", methods=["POST"])
@require_edit_token
def reject_suggestion_route(suggestion_id):
    """
    Reject a pending suggestion. Requires X-Edit-Token.
    ---
    tags:
      - Moderation
    parameters:
      - name: suggestion_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Suggestion rejected.
      404:
        description: No pending suggestion with this id.
    """
    rejected = overrides.reject_suggestion(overrides_con, suggestion_id)
    if not rejected:
        return jsonify({"message": "No pending suggestion found"}), 404
    return jsonify({"id": suggestion_id, "status": "rejected"})


@app.route("/v1/info")
def info():
    """
    Get API version and OpenLibrary dump metadata
    ---
    tags:
      - Info
    responses:
      200:
        description: API and dump info.
    """
    return {
        "name": "openlibrary-local-db-api",
        "version": "1.0.0",
        "docs": request.host_url + "api/docs",
        "oldump_date": os.getenv("OLDUMP_DATE"),
        "overrides_enabled": overrides_con is not None,
        "suggestions_enabled": ENABLE_SUGGESTIONS and overrides_con is not None,
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