from queryai.src.app_core import normalize_db_uri


def test_normalize_db_uri_treats_plain_path_as_sqlite():
	uri = normalize_db_uri("data/example.db")
	assert uri.startswith("sqlite:///")
	assert uri.endswith("data/example.db")


def test_normalize_db_uri_leaves_full_url_unchanged():
	url = "postgresql+psycopg2://user:pass@localhost:5432/dbname"
	assert normalize_db_uri(url) == url


def test_normalize_db_uri_preserves_existing_sqlite_url():
	url = "sqlite:///C:/tmp/test.db"
	assert normalize_db_uri(url) == url
