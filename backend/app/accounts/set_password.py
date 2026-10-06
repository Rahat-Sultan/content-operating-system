"""
Sets or resets the password of an account from the terminal.

    cd backend && ../.venv/bin/python -m app.accounts.set_password you@example.com

The password is typed at a hidden prompt. It is never passed on the command line.
"""
import getpass
import sys

from app.accounts.service import normalize_email
from app.db import SessionLocal
from app.accounts.models import User
from app.settings_security.crypto import MIN_PASSWORD_LENGTH, hash_password


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    email = normalize_email(argv[1])
    password = getpass.getpass("New password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("The two passwords do not match.")
        return 1
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print("No account with that email.")
            return 1
        user.password_hash = hash_password(password)
        user.failed_attempts = 0
        user.locked_until = None
        db.commit()
        print(f"Password set for {email}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
