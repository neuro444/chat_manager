#!/usr/bin/env python3
"""Interactive terminal chatbot.

    python cli.py                 # default user, sqlite
    python cli.py --user sree     # pick a user
    python cli.py --fake          # no API calls, for offline testing
"""
import argparse
import sys

import config
from providers import make_provider
from providers.fake_provider import FakeProvider
from service import build_context, handle_message, stream_message
from storage import make_repo

HELP = """
  <text>            send a message
  /new              start a new session
  /sessions         list your sessions
  /switch <id>      resume a session (id prefix is enough)
  /rename <title>   rename current session
  /delete <id>      delete a session
  /clear            clear current session's messages
  /history          print the transcript
  /summary          show the rolling summary
  /context          inspect the assembled prompt + token counts
  /login <user>     switch user
  /whoami           show current user and session
  /help  /quit
"""


def _resolve(repo, user, prefix):
    for s in repo.list_sessions(user, 100):
        if s.session_id.startswith(prefix):
            return s.session_id
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="default")
    ap.add_argument("--storage", default=None)
    ap.add_argument("--fake", action="store_true", help="use the fake provider")
    ap.add_argument("--no-stream", action="store_true")
    args = ap.parse_args()

    repo = make_repo(args.storage)
    repo.init_db()
    provider = FakeProvider("(fake reply)") if args.fake else make_provider()

    user, sid = args.user, None
    print(f"Chat Manager — user={user} storage={args.storage or config.STORAGE} "
          f"model={'fake' if args.fake else config.LLM_MODEL}")
    print("Type /help for commands.\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0
        if not text:
            continue

        if text.startswith("/"):
            cmd, _, arg = text[1:].partition(" ")
            arg = arg.strip()

            if cmd in ("quit", "exit", "q"):
                print("bye"); return 0
            elif cmd == "help":
                print(HELP)
            elif cmd == "new":
                sid = None; print("(new session — it starts on your next message)")
            elif cmd == "sessions":
                rows = repo.list_sessions(user)
                if not rows:
                    print("(no sessions yet)")
                for s in rows:
                    mark = "*" if s.session_id == sid else " "
                    print(f" {mark} {s.session_id[:8]}  {s.title[:50]}")
            elif cmd == "switch":
                found = _resolve(repo, user, arg)
                if found:
                    sid = found; print(f"(switched to {sid[:8]})")
                else:
                    print("(no such session)")
            elif cmd == "rename":
                if sid and arg:
                    repo.rename_session(sid, arg); print("(renamed)")
                else:
                    print("(need an active session and a title)")
            elif cmd == "delete":
                found = _resolve(repo, user, arg or (sid or ""))
                if found:
                    repo.delete_session(found)
                    if found == sid: sid = None
                    print("(deleted)")
                else:
                    print("(no such session)")
            elif cmd == "clear":
                if sid: repo.clear_session(sid); print("(cleared)")
                else: print("(no active session)")
            elif cmd == "history":
                if not sid: print("(no active session)"); continue
                for m in repo.all_messages(sid):
                    print(f"  [{m.seq}] {m.role}: {m.content[:200]}")
            elif cmd == "summary":
                s = repo.get_session(sid) if sid else None
                print(f"  {s.running_summary or '(none yet)'}" if s else "(no session)")
            elif cmd == "context":
                if not sid:
                    print("(no active session — send a message first)"); continue
                msgs = build_context(repo, user, sid, arg or "(preview)")
                total = 0
                for m in msgs:
                    t = len(m["content"]) // config.CHARS_PER_TOKEN
                    total += t
                    print(f"\n─── {m['role']} (~{t} tokens) ───")
                    print(m["content"][:600])
                print(f"\nTOTAL ≈ {total} tokens (budget {config.MAX_CONTEXT_TOKENS})")
            elif cmd == "login":
                if arg: user, sid = arg, None; print(f"(now {user})")
            elif cmd == "whoami":
                print(f"  user={user}  session={sid[:8] if sid else '(none)'}")
            else:
                print("(unknown command — /help)")
            continue

        # a normal message
        if args.no_stream or args.fake:
            out = handle_message(repo, provider, user, sid, text)
            sid = out["session_id"]
            print(f"bot> {out['answer']}\n")
        else:
            print("bot> ", end="", flush=True)
            gen = stream_message(repo, provider, user, sid, text)
            try:
                for delta in gen:
                    print(delta, end="", flush=True)
            except StopIteration:
                pass
            print("\n")
            sid = repo.list_sessions(user, 1)[0].session_id


if __name__ == "__main__":
    sys.exit(main())
