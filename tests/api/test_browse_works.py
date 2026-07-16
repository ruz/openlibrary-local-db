def _titles(results):
    return {r["title"] for r in results}


def test_list_works_default_sort_title_asc(client):
    resp = client.get("/v1/works")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["results"][0]["title"] == "Empty Work"
    assert data["has_more"] is False


def test_list_works_subject_filter(client):
    resp = client.get("/v1/works?subject=Fantasy")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Lord of the Rings"}


def test_list_works_title_filter(client):
    resp = client.get("/v1/works?title=The")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Lord of the Rings"}


def test_list_works_sort_title_desc(client):
    resp = client.get("/v1/works?sort=title_desc")
    assert resp.status_code == 200
    assert resp.get_json()["results"][0]["title"] == "The Lord of the Rings"


def test_list_works_response_json_fields_are_parsed_lists(client):
    resp = client.get("/v1/works?title=The")
    assert resp.status_code == 200
    result = resp.get_json()["results"][0]
    assert isinstance(result["authors"], list)
    assert isinstance(result["subjects"], list)
    assert isinstance(result["covers"], list)


def test_list_works_excludes_empty_title_by_default(client):
    resp = client.get("/v1/works")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OL12W" not in ol_ids


def test_list_works_include_empty_returns_blank_title_row(client):
    resp = client.get("/v1/works?include_empty=true")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OL12W" in ol_ids


def test_list_works_excludes_whitespace_only_title_by_default(client):
    resp = client.get("/v1/works")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OL13W" not in ol_ids


def test_list_works_include_empty_returns_whitespace_only_title_row(client):
    resp = client.get("/v1/works?include_empty=true")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OL13W" in ol_ids
