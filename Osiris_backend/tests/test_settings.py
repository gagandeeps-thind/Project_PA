"""Configuration loader: secrets from env vars or secret-manager files, DB URL override."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("OSIRIS_ENV", "test")

import settings  # noqa: E402

NAME = "OSIRIS_SETTINGS_TEST_SECRET"


def _clear():
    os.environ.pop(NAME, None)
    os.environ.pop(f"{NAME}_FILE", None)


def test_env_value_wins_over_file():
    _clear()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("from-file\n")
    try:
        os.environ[NAME] = "from-env"
        os.environ[f"{NAME}_FILE"] = f.name
        assert settings.secret(NAME) == "from-env"
    finally:
        _clear()
        os.unlink(f.name)
    print("PASS test_env_value_wins_over_file")


def test_file_value_is_read_and_trimmed():
    _clear()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("  s3cret-value\n")
    try:
        os.environ[f"{NAME}_FILE"] = f.name
        assert settings.secret(NAME) == "s3cret-value"
    finally:
        _clear()
        os.unlink(f.name)
    print("PASS test_file_value_is_read_and_trimmed")


def test_missing_secret_is_none_and_unreadable_file_fails_loudly():
    _clear()
    assert settings.secret(NAME) is None
    os.environ[f"{NAME}_FILE"] = os.path.join(tempfile.gettempdir(), "osiris-missing-secret-file")
    try:
        settings.secret(NAME)
        raise AssertionError("an unreadable secret file must not be treated as unset")
    except RuntimeError as exc:
        assert f"{NAME}_FILE" in str(exc)
    finally:
        _clear()
    print("PASS test_missing_secret_is_none_and_unreadable_file_fails_loudly")


def test_unknown_env_is_production():
    previous = os.environ.get("OSIRIS_ENV")
    try:
        os.environ["OSIRIS_ENV"] = "staging-typo"
        assert not settings.is_dev_env()
        os.environ["OSIRIS_ENV"] = "TEST"
        assert settings.is_dev_env()
    finally:
        os.environ["OSIRIS_ENV"] = previous or "test"
    print("PASS test_unknown_env_is_production")


def test_database_url_override():
    previous = os.environ.pop("OSIRIS_DATABASE_URL", None)
    try:
        assert settings.database_url("sqlite:///default.db") == "sqlite:///default.db"
        os.environ["OSIRIS_DATABASE_URL"] = "postgresql://osiris@db/osiris"
        assert settings.database_url("sqlite:///default.db") == "postgresql://osiris@db/osiris"
    finally:
        os.environ.pop("OSIRIS_DATABASE_URL", None)
        if previous is not None:
            os.environ["OSIRIS_DATABASE_URL"] = previous
    print("PASS test_database_url_override")


def test_only_one_replica_runs_the_scheduler():
    """Behind a load balancer, OSIRIS_RUN_SCHEDULER=0 replicas serve requests but run no jobs."""
    from fastapi.testclient import TestClient

    # A scratch database, so importing the app does not create tables in the dev one.
    os.environ.setdefault("OSIRIS_DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'settings.sqlite3')}")
    os.environ.setdefault("OSIRIS_JWT_SECRET", "settings-test-secret-aaaaaaaaaaaaaaaaaaaaaaaa")
    import main

    previous = os.environ.get("OSIRIS_RUN_SCHEDULER")
    try:
        os.environ["OSIRIS_RUN_SCHEDULER"] = "0"
        assert not settings.run_scheduler()
        with TestClient(main.app) as client:
            assert client.get("/healthz").status_code in (200, 503)
            assert not main.scheduler.running
        os.environ.pop("OSIRIS_RUN_SCHEDULER")
        assert settings.run_scheduler()
    finally:
        os.environ.pop("OSIRIS_RUN_SCHEDULER", None)
        if previous is not None:
            os.environ["OSIRIS_RUN_SCHEDULER"] = previous
    print("PASS test_only_one_replica_runs_the_scheduler")


if __name__ == "__main__":
    test_env_value_wins_over_file()
    test_file_value_is_read_and_trimmed()
    test_missing_secret_is_none_and_unreadable_file_fails_loudly()
    test_unknown_env_is_production()
    test_database_url_override()
    test_only_one_replica_runs_the_scheduler()
