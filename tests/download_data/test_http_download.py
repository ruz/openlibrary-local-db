import gzip
import os

import download_data


class _FakeStreamResponse:
    def __init__(self, data, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers if headers is not None else {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self._data


def test_run_via_http_downloads_decompresses_and_cleans_up(tmp_path, monkeypatch):
    payload = gzip.compress(b"hello world\n")
    monkeypatch.setattr(
        download_data.requests, "get", lambda url, **kwargs: _FakeStreamResponse(payload)
    )

    download_data.run_via_http("authors", "2026-06-30", str(tmp_path))

    txt_path = tmp_path / "ol_dump_authors_2026-06-30.txt"
    assert txt_path.read_bytes() == b"hello world\n"
    assert not (tmp_path / "ol_dump_authors_2026-06-30.txt.gz").exists()
    assert not (tmp_path / "ol_dump_authors_2026-06-30.txt.gz.part").exists()


def test_run_via_http_leaves_partial_file_on_failure_for_later_resume(tmp_path, monkeypatch):
    class _FailingResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            pass

        def raise_for_status(self):
            raise download_data.requests.RequestException("network error")

    monkeypatch.setattr(download_data.requests, "get", lambda url, **kwargs: _FailingResponse())

    try:
        download_data.run_via_http("authors", "2026-06-30", str(tmp_path))
        assert False, "expected DownloadError"
    except download_data.DownloadError:
        pass

    # Nothing was ever written in this case (failure happened before any bytes
    # arrived), so there's still nothing on disk -- but the point is the code
    # path never deletes an existing .part file on failure.
    assert os.listdir(tmp_path) == []


def test_run_via_http_resumes_from_existing_partial_file(tmp_path, monkeypatch):
    full_payload = gzip.compress(b"x" * 100)
    part_path = tmp_path / "ol_dump_authors_2026-06-30.txt.gz.part"
    part_path.write_bytes(full_payload[:20])

    captured_headers = {}

    def fake_get(url, headers=None, **kwargs):
        captured_headers.update(headers or {})
        remaining = full_payload[20:]
        return _FakeStreamResponse(
            remaining,
            status_code=206,
            headers={"Content-Range": f"bytes 20-{len(full_payload) - 1}/{len(full_payload)}"},
        )

    monkeypatch.setattr(download_data.requests, "get", fake_get)

    download_data.run_via_http("authors", "2026-06-30", str(tmp_path))

    assert captured_headers == {"Range": "bytes=20-"}
    txt_path = tmp_path / "ol_dump_authors_2026-06-30.txt"
    assert txt_path.read_bytes() == b"x" * 100
    assert not part_path.exists()


def test_run_via_http_restarts_when_server_ignores_range_header(tmp_path, monkeypatch):
    full_payload = gzip.compress(b"y" * 50)
    part_path = tmp_path / "ol_dump_authors_2026-06-30.txt.gz.part"
    part_path.write_bytes(b"stale-garbage-from-a-different-attempt")

    monkeypatch.setattr(
        download_data.requests, "get",
        lambda url, headers=None, **kwargs: _FakeStreamResponse(full_payload, status_code=200),
    )

    download_data.run_via_http("authors", "2026-06-30", str(tmp_path))

    txt_path = tmp_path / "ol_dump_authors_2026-06-30.txt"
    assert txt_path.read_bytes() == b"y" * 50


def test_run_via_http_skips_download_when_part_file_already_complete(tmp_path, monkeypatch):
    full_payload = gzip.compress(b"z" * 30)
    part_path = tmp_path / "ol_dump_authors_2026-06-30.txt.gz.part"
    part_path.write_bytes(full_payload)

    def fake_get(url, headers=None, **kwargs):
        return _FakeStreamResponse(
            b"", status_code=416,
            headers={"Content-Range": f"bytes */{len(full_payload)}"},
        )

    monkeypatch.setattr(download_data.requests, "get", fake_get)

    download_data.run_via_http("authors", "2026-06-30", str(tmp_path))

    txt_path = tmp_path / "ol_dump_authors_2026-06-30.txt"
    assert txt_path.read_bytes() == b"z" * 30


def test_run_via_http_discards_stale_partial_file_that_does_not_match_remote_size(tmp_path, monkeypatch):
    part_path = tmp_path / "ol_dump_authors_2026-06-30.txt.gz.part"
    part_path.write_bytes(b"stale-bytes-longer-than-remote-file")

    def fake_get(url, headers=None, **kwargs):
        return _FakeStreamResponse(b"", status_code=416, headers={"Content-Range": "bytes */5"})

    monkeypatch.setattr(download_data.requests, "get", fake_get)

    try:
        download_data.run_via_http("authors", "2026-06-30", str(tmp_path))
        assert False, "expected DownloadError"
    except download_data.DownloadError:
        pass

    assert not part_path.exists()


def test_download_all_via_http_fetches_all_three_dump_types(tmp_path, monkeypatch):
    payload = gzip.compress(b"data\n")
    monkeypatch.setattr(
        download_data.requests, "get", lambda url, **kwargs: _FakeStreamResponse(payload)
    )

    download_data._download_all_via_http(str(tmp_path), "2026-06-30")

    for dump_type in download_data.DUMP_TYPES:
        assert (tmp_path / f"ol_dump_{dump_type}_2026-06-30.txt").exists()
