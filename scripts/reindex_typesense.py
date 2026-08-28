"""Backfill existing SQLite chat messages into Typesense."""

import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import make_repo
from storage.typesense_search import get_search


def main() -> None:
    repo = make_repo("sqlite")
    try:
        rows = repo.conn.execute(
            """
            SELECT m.message_id, m.session_id, m.role, m.content, m.created_at,
                   s.user_id
            FROM messages m
            JOIN sessions s ON s.session_id = m.session_id
            WHERE m.role = 'user'
            """
        ).fetchall()

        count = 0
        for row in rows:
            get_search().index_message({
                "message_id": row["message_id"],
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": int(datetime.fromisoformat(row["created_at"]).timestamp()),
            })
            count += 1
            print(f"Indexed: {count}")

        print(f"Total indexed: {count}")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
