def test_get_author_found(client):
    resp = client.get("/v1/author/OL1A")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Jane Doe"


def test_get_author_not_found_404(client):
    resp = client.get("/v1/author/OL999A")
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "Author OL999A not found"


def test_get_author_empty_fields_parsed(client):
    resp = client.get("/v1/author/OL2A")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["alternate_names"] == []
    assert data["bio"] == ""


def test_get_author_photos_filtered_placeholder_kept_in_raw_field(client):
    resp = client.get("/v1/author/OL1A")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["photos"] == [-1, 12345]
