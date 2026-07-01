from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from dotenv import load_dotenv
import os
from flasgger import Swagger
import json

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


load_dotenv()
def get_db_connection():
    print(os.getenv("OL_DB"))
    conn = sqlite3.connect(os.getenv("OL_DB"), check_same_thread=False)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA mmap_size=31000000000;")
    conn.execute("PRAGMA cache_size=-2000000;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn

con = get_db_connection()

@app.route("/v1/search/<query>")
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
      - name: lang
        in: query
        type: string
        description: Language code (e.g., 'eng')
      - name: sort
        in: query
        type: string
        enum: [relevance, newest, oldest]
        default: relevance
    """
    # 1. Get Parameters
    limit = request.args.get("limit", default=10, type=int)
    lang = request.args.get("lang", type=str)
    sort_mode = request.args.get("sort", default="relevance", type=str)

    words = query.split()
    safe_query = " AND ".join([f'"{word.replace('"', '""')}"' for word in words if word])

    # 2. Build Query Components
    base_sql = """
        SELECT e.title, e.isbn_10, e.isbn_13, e.publish_date, e.author_names, e.languages
        FROM editions e
        JOIN editions_fts f ON e.rowid = f.rowid
        WHERE f.editions_fts MATCH ?
    """

    # 2.5 Ensure at least one ISBN is present
    # We check that the JSON array is not empty
    base_sql += " AND (e.isbn_10 != '[]' OR e.isbn_13 != '[]')"

    params = [safe_query]

    # 3. Add Language Filtering
    if lang:
        base_sql += " AND EXISTS (SELECT 1 FROM json_each(e.languages) WHERE value = ?)"
        params.append(lang)

    # 4. Add Sorting Logic
    if sort_mode == "newest":
        base_sql += " ORDER BY e.publish_year DESC"
    elif sort_mode == "oldest":
        # Push year 0 (missing) to the bottom
        base_sql += " ORDER BY e.publish_year = 0, e.publish_year ASC"
    else:
        base_sql += """
            ORDER BY (
                f.rank - (CASE WHEN json_array_length(e.author_names) > 0 THEN 0.5 ELSE 0 END)
            ) DESC
        """

    # 5. Add Limit
    base_sql += " LIMIT ?"
    params.append(limit)

    # 6. Execute and Return
    cur = con.cursor()
    try:
        results = cur.execute(base_sql, params).fetchall()
        if results:
            for row in results:
                json_fields = ['author_names', 'languages', 'isbn_13', 'isbn_10']
                for field in json_fields:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except json.JSONDecodeError:
                            row[field] = [] # Fallback if data is corrupted
            return jsonify(results)
        return jsonify({"message": "Not found"}), 404
    except sqlite3.OperationalError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/v1/edition/<identifier>")
def get_edition(identifier):
    """
    Get full details of a specific edition by OLID, ISBN-10, or ISBN-13
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
    """
    Get full details of a specific edition by OLID, ISBN-10, or ISBN-13.
    Optimized to achieve sub-millisecond execution over 49M rows.
    """
    cur = con.cursor()

    target_ol_id = None

    #isbn_plan = cur.execute("EXPLAIN QUERY PLAN SELECT ol_id FROM isbn_lookup WHERE isbn = ? LIMIT 1", (identifier,)).fetchall()
   # print("ISBN Lookup Plan:", isbn_plan)

    # DEBUG: Check the Editions lookup plan
   #editions_plan = cur.execute("EXPLAIN QUERY PLAN SELECT ol_id FROM editions WHERE ol_id = ? LIMIT 1", (identifier,)).fetchall()
    #print("Editions Lookup Plan:", editions_plan)

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
        return jsonify(result)
    
    return jsonify({"message": f"Edition {identifier} not found"}), 404

@app.route("/v1/work/<ol_id>")
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
            json(authors) as authors,
            json(subjects) as subjects,
            json(subject_people) as subject_people,
            json(subject_places) as subject_places,
            json(covers) as covers,
            json(series) as series
        FROM works
        WHERE ol_id = ?
        LIMIT 1
    """
    cur = con.cursor()

    # Strip the prefix if the user includes it by accident
    clean_id = ol_id.replace("/works/", "")
    result = cur.execute(sql, (clean_id,)).fetchone()

    if result:
        return jsonify(result)
    return jsonify({"message": f"Work {ol_id} not found"}), 404


@app.route("/v1/author/<ol_id>")
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
            json(alternate_names) as alternate_names,
            json(photos) as photos
        FROM authors
        WHERE ol_id = ?
        LIMIT 1
    """
    cur = con.cursor()

    # Strip the prefix if the user includes it by accident
    clean_id = ol_id.replace("/authors/", "")
    result = cur.execute(sql, (clean_id,)).fetchone()

    if result:
        return jsonify(result)
    return jsonify({"message": f"Author {ol_id} not found"}), 404

@app.route("/")
def index():
    if landing_page:
        template_file = os.path.basename(landing_page)
        try:
            return render_template(template_file)
        except Exception as e:
            print(f"Failed to render landing page: {e}")
    return {
        "name": "openlibrary-local-db-api",
        "version": "1.0.0",
        "docs": request.base_url + "docs",
        "oldump_date": os.getenv("OLDUMP_DATE")
    }