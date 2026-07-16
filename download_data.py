import gzip
import os
import re
import shutil
import tempfile
import time

import requests
from tqdm import tqdm

DUMP_TYPES = ("authors", "works", "editions")

ARCHIVE_ORG_SEARCH_URL = "https://archive.org/advancedsearch.php"
ARCHIVE_ORG_COLLECTION = "ol_exports"
IDENTIFIER_RE = re.compile(r"^ol_dump_(\d{4}-\d{2}-\d{2})$")

HTTP_LATEST_URL_TEMPLATE = "https://openlibrary.org/data/ol_dump_{dump_type}_latest.txt.gz"
TORRENT_URL_TEMPLATE = "https://archive.org/download/{identifier}/{identifier}_archive.torrent"
TORRENT_FILENAME_RE = re.compile(r"^ol_dump_(authors|works|editions)_(\d{4}-\d{2}-\d{2})\.txt\.gz$")

HTTP_CONNECT_TIMEOUT = 10
HTTP_READ_TIMEOUT = 60
HTTP_CHUNK_SIZE = 1024 * 1024

TORRENT_STALL_TIMEOUT = 5 * 60      # seconds without progress before giving up
TORRENT_TOTAL_TIMEOUT = 3 * 60 * 60  # hard ceiling for the whole torrent download
TORRENT_POLL_INTERVAL = 2            # seconds between status polls


class DownloadError(Exception):
    """Unrecoverable download failure."""


class TorrentUnavailableError(DownloadError):
    """Torrent path can't proceed; caller should fall back to HTTP in 'auto' mode."""


def resolve_latest_identifier_and_date():
    """
    Queries archive.org's ol_exports collection for the latest full dump
    identifier (ol_dump_YYYY-MM-DD, excluding ol_cdump/ratings/reading-log/
    deprecated variants). Returns (identifier, date_str), or (None, None) on
    any network/parse error or if nothing matches.
    """
    try:
        response = requests.get(
            ARCHIVE_ORG_SEARCH_URL,
            params={
                "q": f"collection:{ARCHIVE_ORG_COLLECTION} AND identifier:ol_dump_*",
                "fl[]": "identifier",
                "sort[]": "publicdate desc",
                "rows": 50,
                "output": "json",
            },
            timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT),
        )
        response.raise_for_status()
        docs = response.json()["response"]["docs"]
    except (requests.RequestException, ValueError, KeyError):
        return None, None

    dates = {}
    for doc in docs:
        identifier = doc.get("identifier", "")
        match = IDENTIFIER_RE.match(identifier)
        if match:
            dates[match.group(1)] = identifier

    if not dates:
        return None, None

    latest_date = sorted(dates)[-1]
    return dates[latest_date], latest_date


def resolve_http_fallback_date():
    """
    HEAD-requests the 'editions' latest dump and parses its Last-Modified
    header into a YYYY-MM-DD string. Returns None on any failure. Used only
    when archive.org search itself is unreachable.
    """
    try:
        response = requests.head(
            HTTP_LATEST_URL_TEMPLATE.format(dump_type="editions"),
            timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT),
            allow_redirects=True,
        )
        response.raise_for_status()
        last_modified = response.headers.get("Last-Modified")
        if not last_modified:
            return None
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(last_modified).date().isoformat()
    except (requests.RequestException, TypeError, ValueError):
        return None


def resolve_canonical_date(explicit_date=None):
    """
    Returns (identifier_or_None, date_str_or_None). If explicit_date is
    given, skips the archive.org lookup entirely (torrent is unusable
    without an identifier in that case). Otherwise tries archive.org search,
    falling back to an HTTP Last-Modified header if that's unreachable.
    """
    if explicit_date:
        return None, explicit_date

    identifier, date_str = resolve_latest_identifier_and_date()
    if date_str is not None:
        return identifier, date_str

    return None, resolve_http_fallback_date()


def decompress_gz_to_txt(gz_path, txt_path):
    with gzip.open(gz_path, "rb") as src, open(txt_path, "wb") as dst:
        shutil.copyfileobj(src, dst)


def run_via_http(dump_type, date_str, input_path):
    """
    Streams the fixed 'latest' HTTP URL for dump_type to
    <input_path>/ol_dump_<dump_type>_<date_str>.txt, decompressing along the
    way. If a partially-downloaded .gz.part file from an earlier interrupted
    run is present, resumes it via an HTTP Range request instead of
    restarting from scratch. Raises DownloadError on failure — the partial
    file is left on disk (unless it's discovered to be stale/corrupt) so a
    subsequent run can resume.
    """
    url = HTTP_LATEST_URL_TEMPLATE.format(dump_type=dump_type)
    gz_path = os.path.join(input_path, f"ol_dump_{dump_type}_{date_str}.txt.gz")
    part_path = gz_path + ".part"
    txt_path = os.path.join(input_path, f"ol_dump_{dump_type}_{date_str}.txt")

    resume_offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
    headers = {"Range": f"bytes={resume_offset}-"} if resume_offset else {}

    try:
        with requests.get(
            url, stream=True, headers=headers, timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
        ) as response:
            if response.status_code == 416:
                # Range not satisfiable: the .part file already covers the
                # whole remote file (e.g. a previous run crashed right after
                # finishing the download but before the rename/decompress
                # step). Nothing left to fetch.
                content_range = response.headers.get("Content-Range", "")
                remote_total = int(content_range.rsplit("/", 1)[-1]) if "/" in content_range else None
                if remote_total is not None and remote_total != resume_offset:
                    os.remove(part_path)
                    raise DownloadError(
                        f"Partial download for {dump_type} doesn't match the remote file size; "
                        "discarded it — re-run to download fresh."
                    )
                total = resume_offset
            else:
                if resume_offset and response.status_code != 206:
                    # Server ignored the Range header (no resume support); start over.
                    resume_offset = 0
                response.raise_for_status()

                content_range = response.headers.get("Content-Range", "")
                if "/" in content_range:
                    total = int(content_range.rsplit("/", 1)[-1])
                elif response.headers.get("Content-Length"):
                    total = resume_offset + int(response.headers["Content-Length"])
                else:
                    total = None

                if resume_offset:
                    print(f"Resuming {dump_type} HTTP download from {resume_offset / (1024 * 1024):.1f} MiB.")

                mode = "ab" if resume_offset else "wb"
                with open(part_path, mode) as f, tqdm(
                    total=total, initial=resume_offset, unit="B", unit_scale=True, unit_divisor=1024,
                    desc=f"{dump_type} (HTTP)",
                ) as bar:
                    for chunk in response.iter_content(chunk_size=HTTP_CHUNK_SIZE):
                        f.write(chunk)
                        bar.update(len(chunk))
    except requests.RequestException as e:
        raise DownloadError(f"HTTP download of {dump_type} dump failed: {e}") from e

    if total is not None and os.path.getsize(part_path) != total:
        raise DownloadError(
            f"HTTP download of {dump_type} dump is incomplete "
            f"({os.path.getsize(part_path)} of {total} bytes); re-run to resume."
        )

    os.replace(part_path, gz_path)
    decompress_gz_to_txt(gz_path, txt_path)
    os.remove(gz_path)
    print(f"Downloaded {dump_type} dump via HTTP ({txt_path}).")


def _download_all_via_http(input_path, date_str):
    for dump_type in DUMP_TYPES:
        run_via_http(dump_type, date_str, input_path)


def select_wanted_files(file_paths, expected_date):
    """
    Pure function (no I/O). file_paths is an ordered list of path strings as
    they appear in the torrent (index = position in that list). Matches each
    against TORRENT_FILENAME_RE and keeps only entries for expected_date.
    Returns {dump_type: index}. Raises TorrentUnavailableError if fewer than
    len(DUMP_TYPES) files are matched.
    """
    wanted = {}
    for index, path in enumerate(file_paths):
        basename = os.path.basename(path)
        match = TORRENT_FILENAME_RE.match(basename)
        if match and match.group(2) == expected_date:
            wanted[match.group(1)] = index

    missing = set(DUMP_TYPES) - set(wanted)
    if missing:
        raise TorrentUnavailableError(
            f"Torrent is missing expected dump file(s) for {expected_date}: {sorted(missing)}"
        )
    return wanted


def fetch_torrent_metainfo(identifier):
    """GETs the .torrent metainfo file and writes it to a temp file, returning its path."""
    url = TORRENT_URL_TEMPLATE.format(identifier=identifier)
    try:
        response = requests.get(url, timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT))
        response.raise_for_status()
    except requests.RequestException as e:
        raise TorrentUnavailableError(f"Could not fetch torrent metainfo: {e}") from e

    fd, torrent_path = tempfile.mkstemp(suffix=".torrent")
    with os.fdopen(fd, "wb") as f:
        f.write(response.content)
    return torrent_path


def run_via_torrent(date_str, identifier, input_path):
    """
    Fetches the .torrent metainfo, selects only the 3 matching dump files,
    and downloads just those via libtorrent. Raises TorrentUnavailableError
    for any condition that should trigger fallback in 'auto' mode.
    """
    if identifier is None:
        raise TorrentUnavailableError("No archive.org identifier available for torrent download.")

    try:
        import libtorrent as lt
    except ImportError as e:
        raise TorrentUnavailableError(f"libtorrent is not available: {e}") from e

    torrent_path = fetch_torrent_metainfo(identifier)
    try:
        ti = lt.torrent_info(torrent_path)
        file_paths = [ti.files().file_path(i) for i in range(ti.num_files())]
        wanted_indices = select_wanted_files(file_paths, date_str)

        file_priorities = [0] * ti.num_files()
        for index in wanted_indices.values():
            file_priorities[index] = 4

        session = lt.session()
        handle = session.add_torrent({
            "ti": ti,
            "save_path": str(input_path),
            "file_priorities": file_priorities,
        })

        start_time = time.monotonic()
        last_progress_time = start_time
        last_downloaded = 0

        with tqdm(
            total=None, unit="B", unit_scale=True, unit_divisor=1024,
            desc="authors+works+editions (torrent)",
        ) as bar:
            while True:
                status = handle.status()
                downloaded = status.total_wanted_done
                total = status.total_wanted

                if bar.total != total:
                    bar.total = total
                    bar.refresh()
                bar.n = downloaded
                bar.refresh()

                if total and downloaded >= total:
                    break

                now = time.monotonic()
                if downloaded > last_downloaded:
                    last_downloaded = downloaded
                    last_progress_time = now

                if now - last_progress_time > TORRENT_STALL_TIMEOUT:
                    raise TorrentUnavailableError(
                        f"Torrent download stalled for over {TORRENT_STALL_TIMEOUT}s."
                    )
                if now - start_time > TORRENT_TOTAL_TIMEOUT:
                    raise TorrentUnavailableError(
                        f"Torrent download exceeded {TORRENT_TOTAL_TIMEOUT}s hard timeout."
                    )

                time.sleep(TORRENT_POLL_INTERVAL)

        session.remove_torrent(handle)

        for dump_type, index in wanted_indices.items():
            downloaded_path = os.path.join(str(input_path), file_paths[index])
            gz_path = os.path.join(str(input_path), f"ol_dump_{dump_type}_{date_str}.txt.gz")
            txt_path = os.path.join(str(input_path), f"ol_dump_{dump_type}_{date_str}.txt")
            if os.path.abspath(downloaded_path) != os.path.abspath(gz_path):
                os.replace(downloaded_path, gz_path)
            decompress_gz_to_txt(gz_path, txt_path)
            os.remove(gz_path)
            print(f"Downloaded {dump_type} dump via BitTorrent ({txt_path}).")

        # Clean up any leftover subdirectories libtorrent created for the multi-file torrent.
        top_level_dir = os.path.join(str(input_path), file_paths[0].split(os.sep)[0])
        if os.path.isdir(top_level_dir) and os.path.abspath(top_level_dir) != os.path.abspath(str(input_path)):
            shutil.rmtree(top_level_dir, ignore_errors=True)
    finally:
        os.remove(torrent_path)


def download_dumps(input_path, method="auto", date=None):
    """
    Downloads authors/works/editions dumps into input_path as
    ol_dump_<type>_<date>.txt (decompressed). method: "auto"|"torrent"|"http".
    Returns the resolved date_str, or None if it could not be determined
    (nothing is downloaded in that case). Raises DownloadError if a forced
    method ("torrent" or "http") fails outright.
    """
    os.makedirs(input_path, exist_ok=True)

    identifier, date_str = resolve_canonical_date(explicit_date=date)
    if date_str is None:
        print("Could not determine the latest OpenLibrary dump date; nothing downloaded.")
        return None

    if date:
        print(f"Fetching OL dump date {date_str} (pinned via --date).")
    else:
        source = f"archive.org identifier {identifier}" if identifier else "HTTP Last-Modified header"
        print(f"Fetching OL dump date {date_str} (auto-detected via {source}; override with --date YYYY-MM-DD if this is wrong).")

    if method == "http":
        _download_all_via_http(input_path, date_str)
        return date_str

    if method == "torrent":
        run_via_torrent(date_str, identifier, input_path)
        return date_str

    # method == "auto": prefer torrent, fall back to HTTP.
    try:
        run_via_torrent(date_str, identifier, input_path)
    except TorrentUnavailableError as e:
        print(f"Torrent download unavailable ({e}); falling back to HTTP.")
        _download_all_via_http(input_path, date_str)

    return date_str
