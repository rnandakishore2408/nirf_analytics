"""Create and manage staff accounts. There is no sign-up page; this script is the only way in.

It talks to the same database as the app (Supabase when SUPABASE_DB_URL is set in .env, else the
local file), so an account created here works on the hosted site straight away.

  python scripts/manage_users.py add <username> "<Display name>" [--role staff|admin]
  python scripts/manage_users.py reset <username>        # new random password
  python scripts/manage_users.py disable <username>
  python scripts/manage_users.py enable <username>
  python scripts/manage_users.py list
  python scripts/manage_users.py events [<username>]     # recent sign-in attempts

New and reset passwords are generated randomly and printed once. Nothing else stores them.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import auth  # noqa: E402
import live_store as store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("username"); a.add_argument("display_name"); a.add_argument("--role", default="staff", choices=["staff", "admin"])
    for c in ("reset", "disable", "enable"):
        sub.add_parser(c).add_argument("username")
    sub.add_parser("list")
    e = sub.add_parser("events"); e.add_argument("username", nargs="?")
    args = ap.parse_args()
    print(f"database: {store.describe()}")

    if args.cmd == "add":
        pw = auth.generate_password()
        auth.create_user(args.username, args.display_name, args.role, pw)
        print(f"created {args.role} '{auth.normalise(args.username)}'\n  password: {pw}\n(shown once; hand it over privately)")
    elif args.cmd == "reset":
        pw = auth.generate_password()
        auth.set_password(args.username, pw)
        print(f"new password for '{auth.normalise(args.username)}': {pw}\n(shown once)")
    elif args.cmd in ("disable", "enable"):
        auth.set_active(args.username, args.cmd == "enable")
        print(f"{args.cmd}d '{auth.normalise(args.username)}'")
    elif args.cmd == "list":
        for u in auth.list_users():
            print(f"  {u['username']:20s} {u['role']:6s} {'active' if u['active'] else 'DISABLED':8s} {u['display_name']}  last sign-in: {u['last_login_at'] or 'never'}")
    elif args.cmd == "events":
        if args.username:
            rows = store.run("SELECT ts, username, success, detail FROM login_events WHERE username = %s ORDER BY ts DESC LIMIT 50",
                             (auth.normalise(args.username),), fetch=True)
        else:
            rows = store.run("SELECT ts, username, success, detail FROM login_events ORDER BY ts DESC LIMIT 50", fetch=True)
        for ts, u, ok, d in rows:
            print(f"  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}  {u:20s} {'OK  ' if ok else 'FAIL'} {d or ''}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as err:
        sys.exit(f"error: {err}")
