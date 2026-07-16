def _titles(results):
    return {r["title"] for r in results}


def test_list_work_editions_returns_linked_editions(client):
    resp = client.get("/v1/work/OL10W/editions?limit=50")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Hobbit", "The Fellowship of the Ring", "El Hobbit"}


def test_list_work_editions_sort_newest(client):
    resp = client.get("/v1/work/OL10W/editions?sort=newest&limit=50")
    assert resp.status_code == 200
    assert resp.get_json()["results"][0]["title"] == "El Hobbit"


def test_list_work_editions_no_links_returns_empty(client):
    resp = client.get("/v1/work/OL11W/editions")
    assert resp.status_code == 200
    assert resp.get_json()["results"] == []


def test_list_work_editions_unknown_work_returns_empty(client):
    resp = client.get("/v1/work/OL999W/editions")
    assert resp.status_code == 200
    assert resp.get_json()["results"] == []


def test_list_author_works_returns_linked_works(client):
    resp = client.get("/v1/author/OL2A/works")
    assert resp.status_code == 200
    titles = _titles(resp.get_json()["results"])
    assert titles == {"The Lord of the Rings"}


def test_list_author_works_no_links_returns_empty(client):
    resp = client.get("/v1/author/OL1A/works")
    assert resp.status_code == 200
    assert resp.get_json()["results"] == []
