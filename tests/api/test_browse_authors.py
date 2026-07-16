def _names(results):
    return {r["name"] for r in results}


def test_list_authors_default_sort_name_asc(client):
    resp = client.get("/v1/authors")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["results"][0]["name"] == "J.R.R. Tolkien"
    assert data["has_more"] is False


def test_list_authors_name_filter(client):
    resp = client.get("/v1/authors?name=Jane")
    assert resp.status_code == 200
    names = _names(resp.get_json()["results"])
    assert names == {"Jane Doe"}


def test_list_authors_sort_name_desc(client):
    resp = client.get("/v1/authors?sort=name_desc")
    assert resp.status_code == 200
    assert resp.get_json()["results"][0]["name"] == "Jane Doe"


def test_list_authors_response_json_fields_are_parsed_lists(client):
    resp = client.get("/v1/authors?name=Jane")
    assert resp.status_code == 200
    result = resp.get_json()["results"][0]
    assert isinstance(result["photos"], list)
