import importlib


def test_index_without_landing_page_returns_info_payload(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "openlibrary-local-db-api"


def test_index_with_landing_page_renders_template(flask_app, monkeypatch, tmp_path):
    template_dir = tmp_path / "landing"
    template_dir.mkdir()
    template_file = template_dir / "index.html"
    template_file.write_text("<html><body>Landing Page</body></html>")

    monkeypatch.setenv("LANDING_PAGE", str(template_file))
    importlib.reload(flask_app)
    try:
        test_client = flask_app.app.test_client()
        resp = test_client.get("/")
        assert resp.status_code == 200
        assert b"Landing Page" in resp.data
    finally:
        monkeypatch.setenv("LANDING_PAGE", "")
        importlib.reload(flask_app)


def test_index_landing_page_render_exception_falls_back_to_info(flask_app, monkeypatch, tmp_path):
    missing_template = tmp_path / "missing.html"
    monkeypatch.setenv("LANDING_PAGE", str(missing_template))
    importlib.reload(flask_app)
    try:
        test_client = flask_app.app.test_client()
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "openlibrary-local-db-api"
    finally:
        monkeypatch.setenv("LANDING_PAGE", "")
        importlib.reload(flask_app)
