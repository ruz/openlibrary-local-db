import json

import overrides


def test_create_and_get_suggestion(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    suggestion = overrides.create_suggestion(
        conn, "works", "OL10W", "patch", {"title": "Fixed Title"}, "typo fix", "hash1"
    )
    assert suggestion["status"] == "pending"
    assert suggestion["action"] == "patch"
    assert json.loads(suggestion["patch"]) == {"title": "Fixed Title"}

    fetched = overrides.get_suggestion(conn, suggestion["id"])
    assert fetched["ol_id"] == "OL10W"


def test_create_delete_suggestion_requires_empty_patch(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "delete", {}, None, "hash1")
    assert suggestion["action"] == "delete"
    assert json.loads(suggestion["patch"]) == {}

    try:
        overrides.create_suggestion(conn, "works", "OL10W", "delete", {"title": "x"}, None, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError:
        pass


def test_create_patch_suggestion_requires_nonempty_patch(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    try:
        overrides.create_suggestion(conn, "works", "OL10W", "patch", {}, None, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError:
        pass


def test_create_suggestion_rejects_unknown_action(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    try:
        overrides.create_suggestion(conn, "works", "OL10W", "bogus", {"title": "x"}, None, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError:
        pass


def test_create_suggestion_rejects_oversized_patch(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    big_value = "x" * (overrides.MAX_SUGGESTION_PATCH_BYTES + 100)
    try:
        overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": big_value}, None, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError as e:
        assert e.status_code == 400


def test_create_suggestion_rejects_oversized_note(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    big_note = "x" * (overrides.MAX_SUGGESTION_NOTE_LENGTH + 10)
    try:
        overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "y"}, big_note, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError:
        pass


def test_pending_cap_enforced_per_record(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    for i in range(overrides.MAX_PENDING_SUGGESTIONS_PER_RECORD):
        overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": f"x{i}"}, None, "hash1")

    try:
        overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "one more"}, None, "hash1")
        assert False, "expected SuggestionError"
    except overrides.SuggestionError as e:
        assert e.status_code == 429


def test_list_suggestions_filters(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "a"}, None, "hash1")
    overrides.create_suggestion(conn, "authors", "OL1A", "patch", {"name": "b"}, None, "hash1")

    assert len(overrides.list_suggestions(conn)) == 2
    assert len(overrides.list_suggestions(conn, entity_type="works")) == 1
    assert len(overrides.list_suggestions(conn, status="pending")) == 2
    assert len(overrides.list_suggestions(conn, status="approved")) == 0


def test_approve_patch_suggestion_creates_override(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    suggestion = overrides.create_suggestion(
        conn, "works", "OL10W", "patch", {"title": "Fixed Title"}, "typo fix", "hash1"
    )
    base_row = {"ol_id": "OL10W", "title": "Original Title"}

    result = overrides.approve_suggestion(conn, suggestion["id"], base_row, "2026-06-30")
    assert result["status"] == "approved"
    assert result["reviewed_at"] is not None

    override = overrides.get_override(conn, "works", "OL10W")
    assert json.loads(override["patch"]) == {"title": "Fixed Title"}


def test_approve_delete_suggestion_discards_existing_override(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    base_row = {"ol_id": "OL10W", "title": "Original Title"}
    overrides.set_override(conn, "works", "OL10W", {"title": "Was Fixed"}, base_row, "2026-06-30")
    assert overrides.get_override(conn, "works", "OL10W") is not None

    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "delete", {}, None, "hash1")
    result = overrides.approve_suggestion(conn, suggestion["id"])
    assert result["status"] == "approved"
    assert overrides.get_override(conn, "works", "OL10W") is None


def test_approve_ignores_non_pending_suggestion(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "x"}, None, "hash1")
    overrides.reject_suggestion(conn, suggestion["id"])

    result = overrides.approve_suggestion(conn, suggestion["id"], {"ol_id": "OL10W", "title": "y"}, "2026-06-30")
    assert result is None
    assert overrides.get_override(conn, "works", "OL10W") is None


def test_reject_suggestion(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    suggestion = overrides.create_suggestion(conn, "works", "OL10W", "patch", {"title": "x"}, None, "hash1")

    assert overrides.reject_suggestion(conn, suggestion["id"]) is True
    row = overrides.get_suggestion(conn, suggestion["id"])
    assert row["status"] == "rejected"
    assert row["reviewed_at"] is not None

    # already-reviewed suggestions can't be rejected again
    assert overrides.reject_suggestion(conn, suggestion["id"]) is False


def test_reject_nonexistent_suggestion(tmp_path):
    conn = overrides.get_overrides_db(str(tmp_path / "overrides.db"))
    assert overrides.reject_suggestion(conn, 99999) is False
