def _titles(results):
    return {r["title"] for r in results}


def test_list_editions_default_sort_title_asc(client):
    resp = client.get("/v1/editions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["results"][0]["title"] == "A Ring and a Promise"
    assert data["has_more"] is True


def test_list_editions_lang_filter(client):
    resp = client.get("/v1/editions?lang=spa")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"El Hobbit"}


def test_list_editions_format_filter(client):
    resp = client.get("/v1/editions?format=Paperback&limit=50")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert "El Hobbit" in titles
    assert "A Ring and a Promise" in titles
    assert "The Hobbit" not in titles


def test_list_editions_year_range_filter(client):
    resp = client.get("/v1/editions?year_min=1950&year_max=1960")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Fellowship of the Ring", "The Two Towers: A Ring Tale"}


def test_list_editions_subject_filter(client):
    resp = client.get("/v1/editions?subject=Fantasy&limit=50")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Hobbit", "The Fellowship of the Ring", "El Hobbit"}


def test_list_editions_title_prefix_filter(client):
    resp = client.get("/v1/editions?title=ring&limit=50")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"Ring of Fire", "Ring Anthology", "Ring Cycle"}


def test_list_editions_sort_newest(client):
    resp = client.get("/v1/editions?sort=newest")
    assert resp.status_code == 200
    assert resp.get_json()["results"][0]["title"] == "A Ring and a Promise"


def test_list_editions_sort_oldest_pushes_zero_year_to_bottom(client):
    resp = client.get("/v1/editions?sort=oldest&limit=50")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert results[0]["title"] == "Gulliver's Travels"
    assert results[-1]["title"] == "Ring Anthology"


def test_list_editions_pagination_has_more(client):
    resp = client.get("/v1/editions?limit=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) == 5
    assert data["has_more"] is True


def test_list_editions_response_json_fields_are_parsed_lists(client):
    resp = client.get("/v1/editions?limit=1")
    assert resp.status_code == 200
    result = resp.get_json()["results"][0]
    assert isinstance(result["author_names"], list)
    assert isinstance(result["languages"], list)
    assert isinstance(result["isbn_10"], list)
    assert isinstance(result["isbn_13"], list)


def test_list_editions_excludes_empty_title_by_default(client):
    resp = client.get("/v1/editions?limit=50")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OLedE1" not in ol_ids


def test_list_editions_include_empty_returns_blank_title_row(client):
    resp = client.get("/v1/editions?limit=50&include_empty=true")
    assert resp.status_code == 200
    ol_ids = {r["ol_id"] for r in resp.get_json()["results"]}
    assert "OLedE1" in ol_ids
