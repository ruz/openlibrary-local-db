import json

import pytest

from process_data import clean, extract_year, filter_image_ids, format_list, normalize_isbn


@pytest.mark.parametrize(
    "date_str,expected",
    [
        ("1555", 1555),
        ("December 31, 1993", 1993),
        ("1973-1977", 1973),
        ("(12 Jun. 2017)", 2017),
        (None, 0),
        ("None", 0),
        ("", 0),
        ("unknown", 0),
        ("9999", 0),
        ("1250", 1250),
    ],
)
def test_extract_year(date_str, expected):
    assert extract_year(date_str) == expected


def test_format_list_empty():
    assert format_list([]) == "[]"


def test_format_list_none():
    assert format_list(None) == "[]"


def test_format_list_non_empty():
    assert json.loads(format_list(["a", "b"])) == ["a", "b"]


def test_clean_none():
    assert clean(None) == ""


def test_clean_empty_string():
    assert clean("") == ""


def test_clean_value_passthrough():
    assert clean("value") == "value"


def test_clean_zero_passthrough():
    assert clean(0) == 0


def test_normalize_isbn_strips_hyphens():
    assert normalize_isbn("0-261-10221-4") == "0261102214"


def test_normalize_isbn_strips_whitespace():
    assert normalize_isbn(" 0261102214 ") == "0261102214"


def test_normalize_isbn_uppercases_check_digit():
    assert normalize_isbn("080442957x") == "080442957X"


def test_filter_image_ids_drops_placeholder():
    assert filter_image_ids([-1, 5, -1, 10]) == [5, 10]


def test_filter_image_ids_empty():
    assert filter_image_ids([]) == []


def test_filter_image_ids_drops_non_int():
    assert filter_image_ids([5, "bad", None, 7]) == [5, 7]


def test_filter_image_ids_all_placeholder():
    assert filter_image_ids([-1, -1]) == []
