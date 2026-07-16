import pytest

import download_data


def test_auto_falls_back_to_http_when_torrent_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        download_data, "resolve_canonical_date",
        lambda explicit_date=None: ("ol_dump_2026-06-30", "2026-06-30"),
    )

    def fail_torrent(date_str, identifier, input_path):
        raise download_data.TorrentUnavailableError("no libtorrent wheel for this platform")

    monkeypatch.setattr(download_data, "run_via_torrent", fail_torrent)

    http_calls = []
    monkeypatch.setattr(
        download_data, "_download_all_via_http",
        lambda input_path, date_str: http_calls.append((input_path, date_str)),
    )

    date_str = download_data.download_dumps(str(tmp_path), method="auto")

    assert date_str == "2026-06-30"
    assert http_calls == [(str(tmp_path), "2026-06-30")]


def test_forced_torrent_method_reraises_instead_of_falling_back(tmp_path, monkeypatch):
    monkeypatch.setattr(
        download_data, "resolve_canonical_date",
        lambda explicit_date=None: ("ol_dump_2026-06-30", "2026-06-30"),
    )

    def fail_torrent(date_str, identifier, input_path):
        raise download_data.TorrentUnavailableError("no libtorrent wheel for this platform")

    monkeypatch.setattr(download_data, "run_via_torrent", fail_torrent)
    monkeypatch.setattr(
        download_data, "_download_all_via_http",
        lambda *a, **k: pytest.fail("HTTP fallback should not run for a forced torrent method"),
    )

    with pytest.raises(download_data.TorrentUnavailableError):
        download_data.download_dumps(str(tmp_path), method="torrent")


def test_run_via_torrent_raises_when_libtorrent_import_fails(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "libtorrent":
            raise ImportError("no wheel available for this platform")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(download_data.TorrentUnavailableError):
        download_data.run_via_torrent("2026-06-30", "ol_dump_2026-06-30", "/tmp/unused")


def test_download_dumps_returns_none_when_date_cannot_be_resolved(tmp_path, monkeypatch):
    monkeypatch.setattr(
        download_data, "resolve_canonical_date",
        lambda explicit_date=None: (None, None),
    )

    assert download_data.download_dumps(str(tmp_path), method="auto") is None
