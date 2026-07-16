import pipeline


def test_creates_env_from_example_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text(
        'FLASK_APP=api.app\n'
        'OL_DB="test.db"\n'
        'OLDUMP_DATE="2024-07-07"\n'
        '#LANDING_PAGE="app/index.html"\n',
        encoding="utf-8",
    )

    pipeline.update_env_file("mydb.db", "2025-05-01")

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'OL_DB="mydb.db"' in content
    assert 'OLDUMP_DATE="2025-05-01"' in content
    assert "FLASK_APP=api.app" in content
    assert '#LANDING_PAGE="app/index.html"' in content


def test_updates_only_managed_keys_in_existing_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        'FLASK_APP=api.app\n'
        'OL_DB="old.db"\n'
        'OLDUMP_DATE="2020-01-01"\n'
        'LANDING_PAGE="index.html"\n'
        'MAX_SEARCH_LIMIT=50\n',
        encoding="utf-8",
    )

    pipeline.update_env_file("new.db", "2025-05-01")

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'OL_DB="new.db"' in content
    assert 'OLDUMP_DATE="2025-05-01"' in content
    assert 'LANDING_PAGE="index.html"' in content
    assert "MAX_SEARCH_LIMIT=50" in content
    assert "old.db" not in content
    assert "2020-01-01" not in content


def test_appends_missing_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('FLASK_APP=api.app\nOL_DB="old.db"\n', encoding="utf-8")

    pipeline.update_env_file("new.db", "2025-05-01")

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'OL_DB="new.db"' in content
    assert 'OLDUMP_DATE="2025-05-01"' in content
