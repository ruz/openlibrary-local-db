def test_info_returns_expected_payload(client):
    resp = client.get("/v1/info")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "openlibrary-local-db-api"
    assert data["version"] == "1.0.0"
    assert data["docs"].endswith("api/docs")
    assert data["oldump_date"] == "2026-06-30"
