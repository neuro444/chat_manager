#!/usr/bin/env python3
"""
Purge sessions (and their messages) older than RETENTION_DAYS from chat_manager''s database.

Design decisions:
  - Purge trigger: session.created_at (when the call started), not updated_at.
  - User records are KEPT: name and preferences survive so returning callers are greeted
    by name even after their transcripts are purged.
  - Only sessions + messages are removed.  The user row itself is untouched unless the
    caller uses the explicit DELETE /callers endpoint (right-to-erasure).
  - Idempotent: safe to re-run.  If a session was already deleted, list_sessions()
    simply won''t return it.

Usage:
    python scripts/purge_old_sessions.py [--dry-run] [--days N]

Cron example (2 AM UTC daily):
    0 2 * * * cd /app && python scripts/purge_old_sessions.py >> /data/logs/purge.log 2>&1
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from storage import make_repo  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

RETENTION_DAYS: int = int(os.getenv("RETENTION_DAYS", "30"))


def _parse_dt(value) -> datetime:
    """Normalise created_at to a UTC-aware datetime regardless of storage format."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def purge(dry_run: bool = False, days: int = RETENTION_DAYS) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    log.info(
        "Purge run started | cutoff=%s | dry_run=%s | backend=%s",
        cutoff.isoformat(),
        dry_run,
        config.STORAGE,
    )

    repo = make_repo(config.STORAGE)
    users_checked = sessions_purged = sessions_kept = 0

    for caller in repo.list_callers():
        user_id = caller["user_id"] if isinstance(caller, dict) else caller.user_id
        sessions = repo.list_sessions(user_id, limit=10_000)
        for session in sessions:
            if _parse_dt(session.created_at) < cutoff:
                if dry_run:
                    log.info(
                        "[DRY RUN] Would delete session %s (user=%s created_at=%s)",
                        session.session_id, user_id, session.created_at,
                    )
                else:
                    repo.delete_session(session.session_id)
                    log.info(
                        "Deleted session %s (user=%s created_at=%s)",
                        session.session_id, user_id, session.created_at,
                    )
                sessions_purged += 1
            else:
                sessions_kept += 1
        users_checked += 1

    log.info(
        "Purge run complete | users_checked=%d | sessions_purged=%d | sessions_kept=%d",
        users_checked, sessions_purged, sessions_kept,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge old chat sessions from chat_manager.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be deleted without making changes.")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS,
                        help=f"Retention window in days (default: {RETENTION_DAYS}).")
    args = parser.parse_args()
    purge(dry_run=args.dry_run, days=args.days)
