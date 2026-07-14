import pytest


@pytest.fixture(autouse=True)
def reset_author_lookup():
    import process_data

    process_data.author_lookup.clear()
    yield
    process_data.author_lookup.clear()
