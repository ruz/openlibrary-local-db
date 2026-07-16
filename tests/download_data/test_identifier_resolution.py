import download_data


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


def _search_response(identifiers):
    return _FakeResponse({"response": {"docs": [{"identifier": i} for i in identifiers]}})


def test_resolve_latest_identifier_filters_decoys_and_picks_max_date(monkeypatch):
    identifiers = [
        "ol_dump_2026-06-30",
        "ol_cdump_2026-06-30",
        "ol_dump_ratings_2026-06-30",
        "ol_dump_reading-log_2026-06-30",
        "ol_dump_2026-05-31",
    ]
    monkeypatch.setattr(download_data.requests, "get", lambda *a, **k: _search_response(identifiers))

    identifier, date_str = download_data.resolve_latest_identifier_and_date()

    assert identifier == "ol_dump_2026-06-30"
    assert date_str == "2026-06-30"


def test_resolve_latest_identifier_returns_none_on_empty_results(monkeypatch):
    monkeypatch.setattr(download_data.requests, "get", lambda *a, **k: _search_response([]))

    assert download_data.resolve_latest_identifier_and_date() == (None, None)


def test_resolve_latest_identifier_returns_none_on_request_error(monkeypatch):
    def raise_error(*a, **k):
        raise download_data.requests.RequestException("boom")

    monkeypatch.setattr(download_data.requests, "get", raise_error)

    assert download_data.resolve_latest_identifier_and_date() == (None, None)


def test_resolve_canonical_date_skips_lookup_when_explicit_date_given(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("archive.org should not be queried when --date is explicit")

    monkeypatch.setattr(download_data.requests, "get", fail_if_called)

    identifier, date_str = download_data.resolve_canonical_date(explicit_date="2025-01-01")

    assert identifier is None
    assert date_str == "2025-01-01"


def test_resolve_canonical_date_falls_back_to_http_last_modified(monkeypatch):
    monkeypatch.setattr(download_data.requests, "get", lambda *a, **k: _search_response([]))

    class _FakeHead:
        headers = {"Last-Modified": "Tue, 30 Jun 2026 00:00:00 GMT"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(download_data.requests, "head", lambda *a, **k: _FakeHead())

    identifier, date_str = download_data.resolve_canonical_date()

    assert identifier is None
    assert date_str == "2026-06-30"
