def test_get_work_found(client):
    resp = client.get("/v1/work/OL10W")
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "The Lord of the Rings"


def test_get_work_not_found_404(client):
    resp = client.get("/v1/work/OL999W")
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "Work OL999W not found"


def test_get_work_empty_fields_parsed(client):
    resp = client.get("/v1/work/OL11W")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["subjects"] == []
    assert data["subject_people"] == []
    assert data["subject_places"] == []
    assert data["covers"] == []
    assert data["series"] == []
