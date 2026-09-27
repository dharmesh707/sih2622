import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest


def pytest_sessionstart(session):
    from backend.app import SemanticModelMissing, get_semantic_model
    try:
        get_semantic_model()
    except SemanticModelMissing as exc:
        pytest.exit(f"{exc}\n(one-time setup, see README 'Provision the semantic model')", returncode=4)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "progresssync.db"
    monkeypatch.setenv("PROGRESSSYNC_DB", str(db_path))
    import backend.app as module
    module.DB_PATH = db_path
    module.init_db()
    yield
