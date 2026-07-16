import pytest

import download_data


REAL_WORLD_STYLE_FILE_LIST = [
    "ol_dump_2026-06-30/ol_dump_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/.____padding_file/0",
    "ol_dump_2026-06-30/ol_dump_2026-06-30_meta.sqlite",
    "ol_dump_2026-06-30/ol_dump_authors_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_covers_metadata_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_deletes_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_editions_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_lists_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_other_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_ratings_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_reading-log_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_redirects_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_wikidata_2026-06-30.txt.gz",
    "ol_dump_2026-06-30/ol_dump_works_2026-06-30.txt.gz",
]


def test_select_wanted_files_picks_only_the_three_full_dumps():
    wanted = download_data.select_wanted_files(REAL_WORLD_STYLE_FILE_LIST, "2026-06-30")

    assert wanted == {
        "authors": REAL_WORLD_STYLE_FILE_LIST.index(
            "ol_dump_2026-06-30/ol_dump_authors_2026-06-30.txt.gz"
        ),
        "editions": REAL_WORLD_STYLE_FILE_LIST.index(
            "ol_dump_2026-06-30/ol_dump_editions_2026-06-30.txt.gz"
        ),
        "works": REAL_WORLD_STYLE_FILE_LIST.index(
            "ol_dump_2026-06-30/ol_dump_works_2026-06-30.txt.gz"
        ),
    }


def test_select_wanted_files_ignores_other_dates():
    file_paths = [
        "ol_dump_2025-01-01/ol_dump_authors_2025-01-01.txt.gz",
        "ol_dump_2025-01-01/ol_dump_works_2025-01-01.txt.gz",
        "ol_dump_2025-01-01/ol_dump_editions_2025-01-01.txt.gz",
    ]
    with pytest.raises(download_data.TorrentUnavailableError):
        download_data.select_wanted_files(file_paths, "2026-06-30")


def test_select_wanted_files_raises_when_fewer_than_three_match():
    file_paths = [
        "ol_dump_2026-06-30/ol_dump_authors_2026-06-30.txt.gz",
        "ol_dump_2026-06-30/ol_dump_works_2026-06-30.txt.gz",
    ]
    with pytest.raises(download_data.TorrentUnavailableError):
        download_data.select_wanted_files(file_paths, "2026-06-30")
