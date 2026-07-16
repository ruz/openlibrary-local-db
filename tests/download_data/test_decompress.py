import gzip

import download_data


def test_decompress_gz_to_txt_round_trips_bytes(tmp_path):
    gz_path = tmp_path / "sample.txt.gz"
    txt_path = tmp_path / "sample.txt"
    gz_path.write_bytes(gzip.compress(b"line one\nline two\n"))

    download_data.decompress_gz_to_txt(str(gz_path), str(txt_path))

    assert txt_path.read_bytes() == b"line one\nline two\n"
