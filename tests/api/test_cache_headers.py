def test_success_response_has_cache_headers(client):
    resp = client.get("/v1/edition/OLedA1")
    assert resp.status_code == 200
    assert resp.headers.get("ETag")
    assert resp.headers.get("Last-Modified")
    assert "public" in resp.headers.get("Cache-Control", "")
    assert "max-age=3600" in resp.headers.get("Cache-Control", "")


def test_conditional_request_with_matching_etag_returns_304(client):
    first = client.get("/v1/edition/OLedA1")
    etag = first.headers.get("ETag")
    assert etag

    second = client.get("/v1/edition/OLedA1", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.data == b""


def test_conditional_request_with_stale_if_modified_since_returns_200(client):
    resp = client.get(
        "/v1/edition/OLedA1",
        headers={"If-Modified-Since": "Mon, 01 Jan 1990 00:00:00 GMT"},
    )
    assert resp.status_code == 200


def test_404_response_has_no_cache_headers(client):
    resp = client.get("/v1/edition/OL999X")
    assert resp.status_code == 404
    assert resp.headers.get("ETag") is None
    assert resp.headers.get("Cache-Control") is None
