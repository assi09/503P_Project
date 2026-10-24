"""Command line for accounts: `python -m app.auth <command>`.

Run on the server, from the repository root. `approve` is also how the owner approves their own
account the first time: sign-up has no email check yet, so an admin email is never approved
automatically (someone else could have registered it first). `set-password` asks for the password
without echoing it, so it never lands in the shell history; it is how the data owner created by
the sync claims their account, and how a forgotten password is replaced until there is a reset.
"""

import argparse
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.auth import accounts
from app.auth.accounts import AuthError
from app.db.models import User
from app.db.session import session_scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pending", help="list sign-ups waiting for approval")
    for name in ("approve", "reject"):
        command = commands.add_parser(name, help=f"{name} a sign-up")
        command.add_argument("email")
    command = commands.add_parser("set-password", help="set or replace an account's password")
    command.add_argument("email")
    args = parser.parse_args(argv)

    with session_scope() as session:
        if args.command == "pending":
            waiting = accounts.pending(session)
            for user in waiting:
                print(f"{user.created_at:%Y-%m-%d %H:%M}  {user.email}")
            print(f"{len(waiting)} waiting")
            return 0
        user = session.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            print(f"No account for {args.email}", file=sys.stderr)
            return 1
        if args.command == "set-password":
            password = getpass.getpass("New password: ")
            if getpass.getpass("Repeat it: ") != password:
                print("The passwords do not match.", file=sys.stderr)
                return 1
            try:
                accounts.set_password(session, user, password)
            except AuthError as error:
                print(error.message, file=sys.stderr)
                return 1
            print(f"Password set for {user.email}; every device was signed out.")
            return 0
        accounts.decide(session, user.id, args.command == "approve", datetime.now(UTC))
        print(f"{user.email}: {user.status}")
        if user.status == "approved":
            print("Also add them as a test user on the Google Cloud console's OAuth screen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
