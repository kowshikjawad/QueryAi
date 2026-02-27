from queryai.src.db_manager import is_read_only_sql


def test_is_read_only_sql_allows_select():
    assert is_read_only_sql("SELECT * FROM users") is True


def test_is_read_only_sql_blocks_dml_and_ddl():
    blocked = [
        "DELETE FROM users",
        "UPDATE users SET name='x'",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN age INT",
        "TRUNCATE TABLE users",
        "INSERT INTO users VALUES (1)",
    ]
    for sql in blocked:
        assert is_read_only_sql(sql) is False
