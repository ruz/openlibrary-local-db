import json
import os

import pytest
import sqlite_utils


def _j(value):
    return json.dumps(value)


AUTHOR_ROWS = [
    {
        "ol_id": "OL1A",
        "name": "Jane Doe",
        "birth_date": "1970",
        "death_date": "",
        "alternate_names": _j(["J. Doe"]),
        "bio": "A test bio",
        "photos": _j([-1, 12345]),
    },
    {
        "ol_id": "OL2A",
        "name": "J.R.R. Tolkien",
        "birth_date": "1892",
        "death_date": "1973",
        "alternate_names": _j([]),
        "bio": "",
        "photos": _j([]),
    },
    # Redirect-stub-style row with no name, for include_empty coverage
    {
        "ol_id": "OL3A",
        "name": "",
        "birth_date": "",
        "death_date": "",
        "alternate_names": _j([]),
        "bio": "",
        "photos": _j([]),
    },
]

WORK_ROWS = [
    {
        "ol_id": "OL10W",
        "title": "The Lord of the Rings",
        "description": "An epic tale",
        "authors": _j(["OL2A"]),
        "subjects": _j(["Fantasy"]),
        "subject_people": _j([]),
        "subject_places": _j(["Middle-earth"]),
        "covers": _j([111]),
        "series": _j(["OL1S"]),
    },
    {
        "ol_id": "OL11W",
        "title": "Empty Work",
        "description": "",
        "authors": _j([]),
        "subjects": _j([]),
        "subject_people": _j([]),
        "subject_places": _j([]),
        "covers": _j([]),
        "series": _j([]),
    },
    # Redirect-stub-style row with no title, for include_empty coverage
    {
        "ol_id": "OL12W",
        "title": "",
        "description": "",
        "authors": _j([]),
        "subjects": _j([]),
        "subject_people": _j([]),
        "subject_places": _j([]),
        "covers": _j([]),
        "series": _j([]),
    },
    # Title that's non-empty but visually blank (whitespace/control bytes only) --
    # real dumps have plenty of these from messy MARC-derived source records.
    {
        "ol_id": "OL13W",
        "title": "\t\x1a  \n",
        "description": "",
        "authors": _j([]),
        "subjects": _j([]),
        "subject_people": _j([]),
        "subject_places": _j([]),
        "covers": _j([]),
        "series": _j([]),
    },
]

EDITION_ROWS = [
    {
        "ol_id": "OLedA1",
        "title": "The Hobbit",
        "subtitle": "",
        "publish_date": "1937",
        "publish_year": 1937,
        "number_of_pages": 310,
        "physical_format": "Hardcover",
        "publishers": _j(["Allen & Unwin"]),
        "isbn_10": _j(["0261102214"]),
        "isbn_13": _j([]),
        "subjects": _j(["Fantasy"]),
        "languages": _j(["eng"]),
        "covers": _j([1]),
        "works": _j(["OL10W"]),
        "authors": _j(["OL2A"]),
        "author_names": _j(["J.R.R. Tolkien"]),
    },
    {
        "ol_id": "OLedA2",
        "title": "The Fellowship of the Ring",
        "subtitle": "",
        "publish_date": "1954",
        "publish_year": 1954,
        "number_of_pages": 423,
        "physical_format": "Hardcover",
        "publishers": _j(["Allen & Unwin"]),
        "isbn_10": _j([]),
        "isbn_13": _j(["9780261102354"]),
        "subjects": _j(["Fantasy"]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j(["OL10W"]),
        "authors": _j(["OL2A"]),
        "author_names": _j(["J.R.R. Tolkien"]),
    },
    {
        "ol_id": "OLedA3",
        "title": "El Hobbit",
        "subtitle": "",
        "publish_date": "1990",
        "publish_year": 1990,
        "number_of_pages": 300,
        "physical_format": "Paperback",
        "publishers": _j(["Minotauro"]),
        "isbn_10": _j(["8445077528"]),
        "isbn_13": _j(["9788445077528"]),
        "subjects": _j(["Fantasy"]),
        "languages": _j(["spa"]),
        "covers": _j([]),
        "works": _j(["OL10W"]),
        "authors": _j(["OL2A"]),
        "author_names": _j(["J.R.R. Tolkien"]),
    },
    # "Ring" titled rows for pagination / sort tests (6 total, incl. OLedA2 above)
    {
        "ol_id": "OLedA5",
        "title": "Ring of Fire",
        "subtitle": "",
        "publish_date": "1888",
        "publish_year": 1888,
        "number_of_pages": 200,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["1111111111"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    {
        "ol_id": "OLedA6",
        "title": "The Two Towers: A Ring Tale",
        "subtitle": "",
        "publish_date": "1955",
        "publish_year": 1955,
        "number_of_pages": 250,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["1111111112"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    {
        "ol_id": "OLedA7",
        "title": "Ring Cycle",
        "subtitle": "",
        "publish_date": "1963",
        "publish_year": 1963,
        "number_of_pages": 150,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["1111111113"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    {
        "ol_id": "OLedA8",
        "title": "A Ring and a Promise",
        "subtitle": "",
        "publish_date": "2020",
        "publish_year": 2020,
        "number_of_pages": 180,
        "physical_format": "Paperback",
        "publishers": _j([]),
        "isbn_10": _j(["1111111114"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    {
        "ol_id": "OLedA10",
        "title": "Ring Anthology",
        "subtitle": "",
        "publish_date": "",
        "publish_year": 0,
        "number_of_pages": 0,
        "physical_format": "",
        "publishers": _j([]),
        "isbn_10": _j(["1111111115"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    # FTS quote-escaping coverage
    {
        "ol_id": "OLedB1",
        "title": "Gulliver's Travels",
        "subtitle": "",
        "publish_date": "1726",
        "publish_year": 1726,
        "number_of_pages": 300,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["9999999991"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    {
        "ol_id": "OLedB2",
        "title": 'The "Great" Escape',
        "subtitle": "",
        "publish_date": "1963",
        "publish_year": 1963,
        "number_of_pages": 300,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["9999999992"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    # Matches a search term but has no isbn -> must be excluded from search results
    {
        "ol_id": "OLedC1",
        "title": "The Phantom Edition",
        "subtitle": "",
        "publish_date": "2000",
        "publish_year": 2000,
        "number_of_pages": 100,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j([]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    # Empty-list JSON fields for /v1/edition parsing test
    {
        "ol_id": "OLedD1",
        "title": "Blank Fields Edition",
        "subtitle": "",
        "publish_date": "2001",
        "publish_year": 2001,
        "number_of_pages": 100,
        "physical_format": "Hardcover",
        "publishers": _j([]),
        "isbn_10": _j(["9999999993"]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j(["eng"]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
    # Redirect-stub-style row with no title, for include_empty coverage
    {
        "ol_id": "OLedE1",
        "title": "",
        "subtitle": "",
        "publish_date": "",
        "publish_year": 0,
        "number_of_pages": 0,
        "physical_format": "",
        "publishers": _j([]),
        "isbn_10": _j([]),
        "isbn_13": _j([]),
        "subjects": _j([]),
        "languages": _j([]),
        "covers": _j([]),
        "works": _j([]),
        "authors": _j([]),
        "author_names": _j([]),
    },
]

ISBN_LOOKUP_ROWS = [
    {"isbn": "0261102214", "ol_id": "OLedA1"},
    {"isbn": "9780261102214", "ol_id": "OLedA1"},
    {"isbn": "9780261102354", "ol_id": "OLedA2"},
    {"isbn": "8445077528", "ol_id": "OLedA3"},
]


def _build_fixture_db(db_path):
    db = sqlite_utils.Database(str(db_path))
    db["authors"].insert_all(AUTHOR_ROWS)
    db["works"].insert_all(WORK_ROWS)
    db["editions"].insert_all(EDITION_ROWS)
    db["isbn_lookup"].insert_all(ISBN_LOOKUP_ROWS)
    db["isbn_lookup"].create_index(["isbn"], unique=True, if_not_exists=True)
    db["editions"].enable_fts(
        ["title", "isbn_10", "isbn_13", "author_names"],
        create_triggers=False,
    )
    for table in ("editions", "works", "authors"):
        db[table].create_index(["ol_id"], if_not_exists=True)
    db.close()


@pytest.fixture(scope="session")
def fixture_db_path(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("fixture_db")
    db_path = db_dir / "test_fixture.db"
    _build_fixture_db(db_path)
    return db_path


@pytest.fixture(scope="session")
def app_env(fixture_db_path):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OL_DB", str(fixture_db_path))
        mp.setenv("OLDUMP_DATE", "2026-06-30")
        mp.setenv("MAX_SEARCH_LIMIT", "100")
        mp.setenv("CACHE_MAX_AGE", "3600")
        # load_dotenv() only refuses to override a key that's already set,
        # so an *absent* LANDING_PAGE would still get filled in from the
        # repo's .env file. Set it to an empty (falsy) string instead.
        mp.setenv("LANDING_PAGE", "")
        yield


@pytest.fixture(scope="session")
def flask_app(app_env):
    import api.app as app_module

    return app_module


@pytest.fixture(scope="session")
def client(flask_app):
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()
