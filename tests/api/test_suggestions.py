import importlib

import pytest


TOKEN_HEADERS = {"X-Edit-Token": "test-token"}


@pytest.fixture()
def suggestions_client(flask_app, fixture_db_path, tmp_path, monkeypatch):
    """A separate app instance with OVERRIDES_DB/EDIT_TOKEN/ENABLE_SUGGESTIONS
    configured, isolated from the session-scoped `client` fixture other API
    test files rely on. Depends on `flask_app` (not a bare module import) so
    api.app is only ever first imported after `app_env` sets OL_DB."""
    monkeypatch.setenv("OL_DB", str(fixture_db_path))
    monkeypatch.setenv("OLDUMP_DATE", "2026-06-30")
    monkeypatch.setenv("OVERRIDES_DB", str(tmp_path / "overrides.db"))
    monkeypatch.setenv("EDIT_TOKEN", "test-token")
    monkeypatch.setenv("ENABLE_SUGGESTIONS", "true")
    monkeypatch.setenv("SUGGESTION_RATE_LIMIT", "1000 per hour")
    monkeypatch.setenv("LANDING_PAGE", "")
    importlib.reload(flask_app)
    flask_app.app.config["TESTING"] = True
    yield flask_app.app.test_client()

    monkeypatch.delenv("OVERRIDES_DB", raising=False)
    monkeypatch.delenv("EDIT_TOKEN", raising=False)
    monkeypatch.delenv("ENABLE_SUGGESTIONS", raising=False)
    monkeypatch.delenv("SUGGESTION_RATE_LIMIT", raising=False)
    importlib.reload(flask_app)


@pytest.fixture()
def rate_limited_client(flask_app, fixture_db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("OL_DB", str(fixture_db_path))
    monkeypatch.setenv("OLDUMP_DATE", "2026-06-30")
    monkeypatch.setenv("OVERRIDES_DB", str(tmp_path / "overrides.db"))
    monkeypatch.setenv("ENABLE_SUGGESTIONS", "true")
    monkeypatch.setenv("SUGGESTION_RATE_LIMIT", "2 per hour")
    monkeypatch.setenv("LANDING_PAGE", "")
    importlib.reload(flask_app)
    flask_app.app.config["TESTING"] = True
    yield flask_app.app.test_client()

    monkeypatch.delenv("OVERRIDES_DB", raising=False)
    monkeypatch.delenv("ENABLE_SUGGESTIONS", raising=False)
    monkeypatch.delenv("SUGGESTION_RATE_LIMIT", raising=False)
    importlib.reload(flask_app)


def test_suggest_disabled_by_default(client):
    resp = client.post("/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"title": "x"}})
    assert resp.status_code == 404


def test_suggest_patch_creates_pending_suggestion_without_affecting_get(suggestions_client):
    resp = suggestions_client.post(
        "/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"title": "Suggested Title"}}
    )
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "pending"

    resp = suggestions_client.get("/v1/work/OL10W")
    assert resp.get_json()["title"] == "The Lord of the Rings"


def test_suggest_unknown_field_rejected(suggestions_client):
    resp = suggestions_client.post("/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"nope": "x"}})
    assert resp.status_code == 400


def test_suggest_bad_action_rejected(suggestions_client):
    resp = suggestions_client.post("/v1/work/OL10W/suggest", json={"action": "bogus"})
    assert resp.status_code == 400


def test_suggest_empty_patch_rejected(suggestions_client):
    resp = suggestions_client.post("/v1/work/OL10W/suggest", json={"action": "patch", "patch": {}})
    assert resp.status_code == 400


def test_suggest_missing_record_404(suggestions_client):
    resp = suggestions_client.post(
        "/v1/work/OL999W/suggest", json={"action": "patch", "patch": {"title": "x"}}
    )
    assert resp.status_code == 404


def test_suggest_delete_action_accepted(suggestions_client):
    resp = suggestions_client.post("/v1/work/OL10W/suggest", json={"action": "delete", "note": "revert please"})
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "pending"


def test_suggest_edition_by_isbn_resolves_canonical_ol_id(suggestions_client):
    resp = suggestions_client.post(
        "/v1/edition/0261102214/suggest", json={"action": "patch", "patch": {"title": "New Title"}}
    )
    assert resp.status_code == 201


def test_pending_cap_returns_429(suggestions_client):
    for i in range(5):
        resp = suggestions_client.post(
            "/v1/work/OL11W/suggest", json={"action": "patch", "patch": {"title": f"x{i}"}}
        )
        assert resp.status_code == 201
    resp = suggestions_client.post(
        "/v1/work/OL11W/suggest", json={"action": "patch", "patch": {"title": "one more"}}
    )
    assert resp.status_code == 429


def test_rate_limit_triggers_429(rate_limited_client):
    for i in range(2):
        resp = rate_limited_client.post(
            "/v1/work/OL11W/suggest", json={"action": "patch", "patch": {"title": f"x{i}"}}
        )
        assert resp.status_code == 201
    resp = rate_limited_client.post(
        "/v1/work/OL11W/suggest", json={"action": "patch", "patch": {"title": "one more"}}
    )
    assert resp.status_code == 429


def test_list_suggestions_requires_edit_token(suggestions_client):
    resp = suggestions_client.get("/v1/suggestions")
    assert resp.status_code == 404

    resp = suggestions_client.get("/v1/suggestions", headers=TOKEN_HEADERS)
    assert resp.status_code == 200


def test_approve_patch_suggestion_applies_override(suggestions_client):
    resp = suggestions_client.post(
        "/v1/author/OL2A/suggest", json={"action": "patch", "patch": {"name": "J.R.R. Tolkien Jr."}}
    )
    suggestion_id = resp.get_json()["id"]

    resp = suggestions_client.post(f"/v1/suggestions/{suggestion_id}/approve", headers=TOKEN_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "approved"

    resp = suggestions_client.get("/v1/author/OL2A")
    assert resp.get_json()["name"] == "J.R.R. Tolkien Jr."


def test_approve_delete_suggestion_reverts_override(suggestions_client):
    resp = suggestions_client.post(
        "/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"title": "Temp Title"}}
    )
    patch_suggestion_id = resp.get_json()["id"]
    suggestions_client.post(f"/v1/suggestions/{patch_suggestion_id}/approve", headers=TOKEN_HEADERS)
    assert suggestions_client.get("/v1/work/OL10W").get_json()["title"] == "Temp Title"

    resp = suggestions_client.post("/v1/work/OL10W/suggest", json={"action": "delete"})
    delete_suggestion_id = resp.get_json()["id"]
    resp = suggestions_client.post(f"/v1/suggestions/{delete_suggestion_id}/approve", headers=TOKEN_HEADERS)
    assert resp.status_code == 200

    resp = suggestions_client.get("/v1/work/OL10W")
    data = resp.get_json()
    assert data["title"] == "The Lord of the Rings"
    assert "_override_status" not in data


def test_list_works_excludes_title_blanked_by_override(suggestions_client):
    resp = suggestions_client.post(
        "/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"title": ""}}
    )
    suggestion_id = resp.get_json()["id"]
    resp = suggestions_client.post(f"/v1/suggestions/{suggestion_id}/approve", headers=TOKEN_HEADERS)
    assert resp.status_code == 200

    resp = suggestions_client.get("/v1/works")
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OL10W" not in ol_ids

    resp = suggestions_client.get("/v1/works?include_empty=true")
    results = {r["ol_id"]: r for r in resp.get_json()["results"]}
    assert results["OL10W"]["title"] == ""


def test_reject_suggestion_never_applied_and_excluded_from_pending_list(suggestions_client):
    resp = suggestions_client.post(
        "/v1/work/OL10W/suggest", json={"action": "patch", "patch": {"title": "Should Not Apply"}}
    )
    suggestion_id = resp.get_json()["id"]

    resp = suggestions_client.post(f"/v1/suggestions/{suggestion_id}/reject", headers=TOKEN_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "rejected"

    resp = suggestions_client.get("/v1/work/OL10W")
    assert resp.get_json()["title"] == "The Lord of the Rings"

    resp = suggestions_client.get("/v1/suggestions?status=pending", headers=TOKEN_HEADERS)
    ids = [s["id"] for s in resp.get_json()["suggestions"]]
    assert suggestion_id not in ids


def test_approve_nonexistent_suggestion_404(suggestions_client):
    resp = suggestions_client.post("/v1/suggestions/999999/approve", headers=TOKEN_HEADERS)
    assert resp.status_code == 404


def test_reject_nonexistent_suggestion_404(suggestions_client):
    resp = suggestions_client.post("/v1/suggestions/999999/reject", headers=TOKEN_HEADERS)
    assert resp.status_code == 404


def test_old_direct_patch_route_no_longer_exists(suggestions_client):
    resp = suggestions_client.patch("/v1/work/OL10W", json={"title": "x"}, headers=TOKEN_HEADERS)
    assert resp.status_code == 405
