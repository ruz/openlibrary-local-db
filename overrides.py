import json
import os
import sqlite3
from datetime import datetime, timezone

ENTITY_TYPES = ("authors", "works", "editions")

# Real OL key prefixes as seen in the raw dumps (editions use /books/, not /editions/).
ENTITY_KEY_PREFIX = {
    "authors": "/authors/",
    "works": "/works/",
    "editions": "/books/",
}

OVERRIDES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS overrides (
    entity_type    TEXT NOT NULL,
    ol_id          TEXT NOT NULL,
    patch          TEXT NOT NULL,
    base_snapshot  TEXT NOT NULL,
    base_dump_date TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    note           TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    submitted_at   TEXT,
    PRIMARY KEY (entity_type, ol_id)
);
"""

SUGGESTION_ACTIONS = ("patch", "delete")

SUGGESTIONS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS suggestions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type    TEXT NOT NULL,
    ol_id          TEXT NOT NULL,
    action         TEXT NOT NULL DEFAULT 'patch',
    patch          TEXT NOT NULL DEFAULT '{}',
    note           TEXT,
    submitter_hash TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL,
    reviewed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status);
"""

# Anti-abuse caps on public suggestions. Deliberately hardcoded rather than
# env-configurable -- these guard against pathological payloads/flooding, not
# values an operator would plausibly want to tune per deployment.
MAX_SUGGESTION_PATCH_BYTES = 4000
MAX_SUGGESTION_NOTE_LENGTH = 500
MAX_PENDING_SUGGESTIONS_PER_RECORD = 5


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_overrides_db(path=None):
    """Open (creating if needed) the overrides database. Returns None if no
    path was given and OVERRIDES_DB isn't set — the sentinel callers check to
    treat the whole feature as disabled."""
    path = path or os.getenv("OVERRIDES_DB")
    if not path:
        return None
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = _dict_factory
    conn.execute(OVERRIDES_SCHEMA_SQL)
    conn.executescript(SUGGESTIONS_SCHEMA_SQL)
    conn.commit()
    return conn


def get_override(conn, entity_type, ol_id):
    return conn.execute(
        "SELECT * FROM overrides WHERE entity_type = ? AND ol_id = ?",
        (entity_type, ol_id),
    ).fetchone()


def list_overrides(conn, status=None, entity_type=None):
    query = "SELECT * FROM overrides WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY entity_type, ol_id"
    return conn.execute(query, params).fetchall()


def set_override(conn, entity_type, ol_id, patch, base_row, dump_date, note=None):
    """Upsert an override. base_row must be a mapping of the *current* base
    table row (only the keys present in patch are snapshotted). Merges with
    any existing override rather than replacing it, so patching one field
    doesn't discard previously overridden fields on the same record."""
    new_snapshot = {k: base_row.get(k) for k in patch}
    now = _now()
    existing = get_override(conn, entity_type, ol_id)
    if existing:
        created_at = existing["created_at"]
        merged_patch = {**json.loads(existing["patch"]), **patch}
        merged_snapshot = {**json.loads(existing["base_snapshot"]), **new_snapshot}
    else:
        created_at = now
        merged_patch = patch
        merged_snapshot = new_snapshot
    patch, base_snapshot = merged_patch, merged_snapshot
    conn.execute(
        """
        INSERT INTO overrides
            (entity_type, ol_id, patch, base_snapshot, base_dump_date, status, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        ON CONFLICT(entity_type, ol_id) DO UPDATE SET
            patch = excluded.patch,
            base_snapshot = excluded.base_snapshot,
            base_dump_date = excluded.base_dump_date,
            status = 'active',
            note = excluded.note,
            updated_at = excluded.updated_at
        """,
        (
            entity_type, ol_id, json.dumps(patch), json.dumps(base_snapshot),
            dump_date, note, created_at, now,
        ),
    )
    conn.commit()
    return get_override(conn, entity_type, ol_id)


def discard_override(conn, entity_type, ol_id):
    cur = conn.execute(
        "DELETE FROM overrides WHERE entity_type = ? AND ol_id = ?",
        (entity_type, ol_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_submitted(conn, entity_type, ol_id):
    now = _now()
    cur = conn.execute(
        "UPDATE overrides SET status = 'submitted', submitted_at = ?, updated_at = ? "
        "WHERE entity_type = ? AND ol_id = ?",
        (now, now, entity_type, ol_id),
    )
    conn.commit()
    return cur.rowcount > 0


def clear_overrides(conn):
    conn.execute("DELETE FROM overrides")
    conn.commit()


def sync_overrides(overrides_conn, base_db_path):
    """Re-check every active override against the freshly imported base DB.
    Flips status to 'stale' if any patched field's upstream value has drifted
    from the snapshot taken when the override was made, or 'orphaned' if the
    base record no longer exists at all. base_snapshot is left untouched so
    the original diff stays inspectable."""
    base_conn = sqlite3.connect(base_db_path)
    base_conn.row_factory = _dict_factory
    stale_count = 0
    orphaned_count = 0
    try:
        for row in list_overrides(overrides_conn, status="active"):
            entity_type = row["entity_type"]
            ol_id = row["ol_id"]
            base_snapshot = json.loads(row["base_snapshot"])
            fields = list(base_snapshot.keys())
            columns = ", ".join(fields)
            try:
                base_row = base_conn.execute(
                    f"SELECT {columns} FROM {entity_type} WHERE ol_id = ?",
                    (ol_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                base_row = None

            now = _now()
            if base_row is None:
                overrides_conn.execute(
                    "UPDATE overrides SET status = 'orphaned', updated_at = ? "
                    "WHERE entity_type = ? AND ol_id = ?",
                    (now, entity_type, ol_id),
                )
                orphaned_count += 1
                continue

            drifted = any(base_row.get(f) != base_snapshot.get(f) for f in fields)
            if drifted:
                overrides_conn.execute(
                    "UPDATE overrides SET status = 'stale', updated_at = ? "
                    "WHERE entity_type = ? AND ol_id = ?",
                    (now, entity_type, ol_id),
                )
                stale_count += 1
        overrides_conn.commit()
    finally:
        base_conn.close()
    return {"stale": stale_count, "orphaned": orphaned_count}


def resolve_override(conn, entity_type, ol_id, action):
    """action is one of 'keep-mine', 'accept-upstream', 'discard'.
    'accept-upstream' and 'discard' both drop the override — the difference
    is intent (deferring to OL's new value vs. abandoning the correction),
    not mechanics. 'keep-mine' just clears a stale/orphaned flag."""
    if action in ("discard", "accept-upstream"):
        return discard_override(conn, entity_type, ol_id)
    if action == "keep-mine":
        now = _now()
        cur = conn.execute(
            "UPDATE overrides SET status = 'active', updated_at = ? "
            "WHERE entity_type = ? AND ol_id = ?",
            (now, entity_type, ol_id),
        )
        conn.commit()
        return cur.rowcount > 0
    raise ValueError(f"Unknown resolve action: {action!r}")


def export_overrides(conn, output_path, status="active"):
    rows = list_overrides(conn, status=status)
    data = [
        {
            "entity_type": row["entity_type"],
            "ol_key": f"{ENTITY_KEY_PREFIX[row['entity_type']]}{row['ol_id']}",
            "ol_id": row["ol_id"],
            "patch": json.loads(row["patch"]),
            "note": row["note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return len(data)


class SuggestionError(ValueError):
    """Raised for invalid suggestion input (bad action, oversized payload, too
    many pending suggestions for a record). `status_code` tells the caller
    which HTTP status to map it to (400 for bad input, 429 for the pending cap)."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def count_pending_suggestions(conn, entity_type, ol_id):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM suggestions WHERE entity_type = ? AND ol_id = ? AND status = 'pending'",
        (entity_type, ol_id),
    ).fetchone()
    return row["n"]


def create_suggestion(conn, entity_type, ol_id, action, patch, note, submitter_hash):
    if action not in SUGGESTION_ACTIONS:
        raise SuggestionError(f"Unknown action: {action!r}")
    patch = patch or {}
    if action == "delete" and patch:
        raise SuggestionError("'delete' suggestions cannot include a patch")
    if action == "patch" and not patch:
        raise SuggestionError("'patch' suggestions require a non-empty patch")
    if len(json.dumps(patch)) > MAX_SUGGESTION_PATCH_BYTES:
        raise SuggestionError("Patch is too large")
    if note and len(note) > MAX_SUGGESTION_NOTE_LENGTH:
        raise SuggestionError("Note is too long")
    if count_pending_suggestions(conn, entity_type, ol_id) >= MAX_PENDING_SUGGESTIONS_PER_RECORD:
        raise SuggestionError("Too many pending suggestions for this record", status_code=429)

    now = _now()
    cur = conn.execute(
        """
        INSERT INTO suggestions (entity_type, ol_id, action, patch, note, submitter_hash, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (entity_type, ol_id, action, json.dumps(patch), note, submitter_hash, now),
    )
    conn.commit()
    return get_suggestion(conn, cur.lastrowid)


def get_suggestion(conn, suggestion_id):
    return conn.execute(
        "SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()


def list_suggestions(conn, status=None, entity_type=None):
    query = "SELECT * FROM suggestions WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY created_at"
    return conn.execute(query, params).fetchall()


def approve_suggestion(conn, suggestion_id, base_row=None, dump_date=None):
    """Promote a pending suggestion into the real overrides table. For a
    'patch' suggestion, base_row/dump_date must be supplied (the caller's
    current read of the base DB, same as for a direct set_override call).
    For a 'delete' suggestion, they're ignored -- it just discards whatever
    override currently exists for the record."""
    suggestion = get_suggestion(conn, suggestion_id)
    if suggestion is None or suggestion["status"] != "pending":
        return None

    if suggestion["action"] == "patch":
        patch = json.loads(suggestion["patch"])
        set_override(
            conn, suggestion["entity_type"], suggestion["ol_id"], patch,
            base_row, dump_date, note=suggestion["note"],
        )
    else:
        discard_override(conn, suggestion["entity_type"], suggestion["ol_id"])

    now = _now()
    conn.execute(
        "UPDATE suggestions SET status = 'approved', reviewed_at = ? WHERE id = ?",
        (now, suggestion_id),
    )
    conn.commit()
    return get_suggestion(conn, suggestion_id)


def reject_suggestion(conn, suggestion_id):
    now = _now()
    cur = conn.execute(
        "UPDATE suggestions SET status = 'rejected', reviewed_at = ? WHERE id = ? AND status = 'pending'",
        (now, suggestion_id),
    )
    conn.commit()
    return cur.rowcount > 0
