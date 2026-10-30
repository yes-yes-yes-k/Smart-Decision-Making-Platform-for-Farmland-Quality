import os


def test_load_pg_test_environment_uses_isolated_database(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DB_HOST=localhost\n"
        "DB_PORT=5432\n"
        "DB_USER=postgres\n"
        "DB_PASSWORD=secret\n"
        "DB_NAME=db_enterprise_qa\n",
        encoding="utf-8",
    )
    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(key, raising=False)

    from tests.pg_test_config import load_pg_test_environment

    test_db = load_pg_test_environment(env_file)

    assert test_db == "db_enterprise_qa_test"
    assert os.environ["DB_NAME"] == "db_enterprise_qa_test"
    assert os.environ["DB_PASSWORD"] == "secret"
