def _titles(results):
    return {r["title"] for r in results}


def test_search_by_title_word_returns_match(client):
    resp = client.get("/v1/search/hobbit")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert "The Hobbit" in titles
    assert "El Hobbit" in titles


def test_search_excludes_editions_with_no_isbn(client):
    resp = client.get("/v1/search/phantom")
    assert resp.status_code == 404


def test_search_lang_filter_eng(client):
    resp = client.get("/v1/search/hobbit?lang=eng")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Hobbit"}


def test_search_lang_filter_spa(client):
    resp = client.get("/v1/search/hobbit?lang=spa")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"El Hobbit"}


def test_search_sort_newest(client):
    resp = client.get("/v1/search/ring?sort=newest&limit=10")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert results[0]["title"] == "A Ring and a Promise"


def test_search_sort_oldest_pushes_zero_year_to_bottom(client):
    resp = client.get("/v1/search/ring?sort=oldest&limit=10")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert results[0]["title"] == "Ring of Fire"
    assert results[-1]["title"] == "Ring Anthology"


def test_search_sort_relevance_default(client):
    resp = client.get("/v1/search/ring")
    assert resp.status_code == 200


def test_search_pagination_has_more_true(client):
    resp = client.get("/v1/search/ring?limit=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) == 5
    assert data["has_more"] is True


def test_search_pagination_offset_returns_remainder(client):
    resp = client.get("/v1/search/ring?limit=5&offset=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) == 1
    assert data["has_more"] is False


def test_search_offset_beyond_results_returns_200_empty(client):
    resp = client.get("/v1/search/ring?offset=100")
    assert resp.status_code == 200
    assert resp.get_json()["results"] == []


def test_search_no_results_first_page_returns_404(client):
    resp = client.get("/v1/search/zzzznonexistentzzzz")
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "Not found"


def test_search_limit_invalid_defaults_to_10(client):
    resp = client.get("/v1/search/ring?limit=-5")
    assert resp.status_code == 200
    assert resp.get_json()["limit"] == 10


def test_search_limit_clamped_to_max(client):
    resp = client.get("/v1/search/ring?limit=9999")
    assert resp.status_code == 200
    assert resp.get_json()["limit"] == 100


def test_search_offset_negative_defaults_to_zero(client):
    resp = client.get("/v1/search/ring?offset=-1")
    assert resp.status_code == 200
    assert resp.get_json()["offset"] == 0


def test_search_apostrophe_in_query_does_not_error(client):
    resp = client.get("/v1/search/gulliver's")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert "Gulliver's Travels" in titles


def test_search_double_quote_in_query_does_not_error(client):
    resp = client.get('/v1/search/great"')
    assert resp.status_code in (200, 404)


def test_search_response_json_fields_are_parsed_lists(client):
    resp = client.get("/v1/search/hobbit?lang=eng")
    assert resp.status_code == 200
    result = resp.get_json()["results"][0]
    assert isinstance(result["author_names"], list)
    assert isinstance(result["languages"], list)
    assert isinstance(result["isbn_10"], list)
    assert isinstance(result["isbn_13"], list)
