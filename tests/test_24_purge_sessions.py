"""Tests for the 30-day session purge script (chat_manager).

All tests run in-process against the in-memory store — no SQLite file, no network.
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: make sure the script is importable from the repo root
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# We import the purge function, not __main__, so no side-effects on import.
import scripts.purge_old_sessions as purge_module  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _session(session_id: str, user_id: str, days_ago: int):
    """Return a minimal Session-like object with a UTC-aware created_at."""
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return SimpleNamespace(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at,
    )


def _caller(user_id: str):
    return {"user_id": user_id}


def _make_repo(callers, sessions_by_user):
    """Build a mock ChatRepository with controlled data."""
    repo = MagicMock()
    repo.list_callers.return_value = [_caller(uid) for uid in callers]
    repo.list_sessions.side_effect = lambda uid, limit=50: sessions_by_user.get(uid, [])
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestPurgeSessions:
    def test_old_sessions_are_deleted(self):
        """Sessions older than the retention window must be deleted."""
        old = _session("sess-old", "user-1", days_ago=31)
        repo = _make_repo(["user-1"], {"user-1": [old]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_session.assert_called_once_with("sess-old")

    def test_recent_sessions_are_kept(self):
        """Sessions within the retention window must NOT be deleted."""
        recent = _session("sess-new", "user-1", days_ago=10)
        repo = _make_repo(["user-1"], {"user-1": [recent]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_session.assert_not_called()

    def test_boundary_exactly_30_days_is_purged(self):
        """A session created exactly 30 days ago is at or before the cutoff and must be purged.

        cutoff = now - 30 days.  created_at = now - 30 days.
        Because `timedelta(days=30)` is computed separately for both the cutoff
        and the session, created_at will be very slightly older than cutoff in
        practice (a few microseconds of execution time), so the session is purged.
        """
        exact = _session("sess-exact", "user-1", days_ago=30)
        repo = _make_repo(["user-1"], {"user-1": [exact]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_session.assert_called_once_with("sess-exact")

    def test_dry_run_never_deletes(self):
        """--dry-run must not call delete_session even for expired sessions."""
        old = _session("sess-old", "user-1", days_ago=60)
        repo = _make_repo(["user-1"], {"user-1": [old]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=True, days=30)

        repo.delete_session.assert_not_called()

    def test_user_records_are_never_deleted(self):
        """Purge only removes sessions; user rows must be untouched."""
        old = _session("sess-old", "user-1", days_ago=60)
        repo = _make_repo(["user-1"], {"user-1": [old]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_user.assert_not_called()

    def test_multiple_users_and_mixed_sessions(self):
        """Old sessions for multiple users are all purged; recent ones kept."""
        sessions_by_user = {
            "user-a": [
                _session("old-a", "user-a", days_ago=35),
                _session("new-a", "user-a", days_ago=5),
            ],
            "user-b": [
                _session("old-b", "user-b", days_ago=45),
            ],
        }
        repo = _make_repo(["user-a", "user-b"], sessions_by_user)

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        deleted = {call.args[0] for call in repo.delete_session.call_args_list}
        assert deleted == {"old-a", "old-b"}

    def test_empty_database_runs_without_error(self):
        """No callers → no iterations → no errors."""
        repo = _make_repo([], {})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_session.assert_not_called()

    def test_naive_datetime_is_treated_as_utc(self):
        """Timezone-naive created_at strings (legacy data) are assumed UTC."""
        # Simulate a naive datetime (no tzinfo)
        session = SimpleNamespace(
            session_id="sess-naive",
            user_id="user-1",
            created_at=datetime.utcnow() - timedelta(days=40),  # naive, old
        )
        repo = _make_repo(["user-1"], {"user-1": [session]})

        with patch.object(purge_module, "make_repo", return_value=repo):
            purge_module.purge(dry_run=False, days=30)

        repo.delete_session.assert_called_once_with("sess-naive")
