"""Layer 14 — configuration paths.

A cwd-relative SQLITE_PATH silently creates a fresh empty database when the
server starts from a different directory. That is indistinguishable from data
loss, so the path must be absolute and stable.
"""
import subprocess
import sys
from pathlib import Path

import config

REPO = Path(__file__).resolve().parents[1]


def test_sqlite_path_is_absolute():
    assert Path(config.SQLITE_PATH).is_absolute()


def test_sqlite_path_is_inside_project():
    assert str(config.SQLITE_PATH).startswith(str(config.BASE_DIR))


def test_sqlite_path_identical_from_any_cwd():
    """The regression that lost the demo chats."""
    code = "import sys; sys.path.insert(0, r'%s'); import config; print(config.SQLITE_PATH)" % REPO
    out = subprocess.run([sys.executable, "-c", code], cwd="/tmp",
                         capture_output=True, text=True).stdout.strip()
    assert out == config.SQLITE_PATH


def test_absolute_env_value_is_respected(monkeypatch, tmp_path):
    import importlib
    custom = tmp_path / "elsewhere.db"
    monkeypatch.setenv("SQLITE_PATH", str(custom))
    reloaded = importlib.reload(config)
    assert reloaded.SQLITE_PATH == str(custom)
    monkeypatch.delenv("SQLITE_PATH")
    importlib.reload(config)


def test_data_survives_across_store_instances():
    """Two stores opened by path must see the same rows — the durability claim."""
    import tempfile

    from storage.sqlite_store import SQLiteStore
    db = str(Path(tempfile.mkdtemp()) / "persist.db")
    a = SQLiteStore(db); a.init_db()
    s = a.create_session("+91999", "call one")
    a.append_message(s.session_id, "user", "two samosas")
    a.close()

    b = SQLiteStore(db); b.init_db()
    assert [m.content for m in b.all_messages(s.session_id)] == ["two samosas"]
    assert b.list_sessions("+91999")[0].title == "call one"
    b.close()
