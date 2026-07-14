def test_get_edition_by_ol_id_found(client):
    resp = client.get("/v1/edition/OLedA1")
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "The Hobbit"


def test_get_edition_by_isbn10_found(client):
    resp = client.get("/v1/edition/0261102214")
    assert resp.status_code == 200
    assert resp.get_json()["ol_id"] == "OLedA1"


def test_get_edition_by_isbn13_found(client):
    resp = client.get("/v1/edition/9780261102354")
    assert resp.status_code == 200
    assert resp.get_json()["ol_id"] == "OLedA2"


def test_get_edition_second_isbn_same_edition(client):
    resp = client.get("/v1/edition/9780261102214")
    assert resp.status_code == 200
    assert resp.get_json()["ol_id"] == "OLedA1"


def test_get_edition_unknown_ol_id_404(client):
    resp = client.get("/v1/edition/OL999X")
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "Edition OL999X not found"


def test_get_edition_unknown_isbn_404(client):
    resp = client.get("/v1/edition/0000000000")
    assert resp.status_code == 404


def test_get_edition_empty_list_fields_parsed(client):
    resp = client.get("/v1/edition/OLedD1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["authors"] == []
    assert data["author_names"] == []
