"""
Lightweight smoke test for the authentication helpers.
This script does NOT import the Kivy app; it exercises the DB, Argon2 hashing,
TOTP generation/verification, and session creation/validation using sqlite.

Run from the project root (Windows cmd):
    python services\auth_smoke_test.py

It creates/uses users.db in the project working directory.
"""
from pathlib import Path
import sqlite3
import datetime
import secrets

from argon2 import PasswordHasher
from argon2.low_level import Type
import pyotp

PH = PasswordHasher(type=Type.ID)
DB = "users.db"

CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password TEXT,
    totp_secret TEXT
)
"""

CREATE_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    token TEXT UNIQUE,
    expires_at INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
"""


def ensure_db():
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute(CREATE_USERS_SQL)
        cur.execute(CREATE_SESSIONS_SQL)
        conn.commit()


def signup(email, password):
    pwd_hash = PH.hash(password)
    secret = pyotp.random_base32()
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password, totp_secret) VALUES (?, ?, ?)",
                    (email, pwd_hash, secret))
        conn.commit()
    return secret


def verify_password(email, password):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if not row:
            return False
        stored_hash = row[0]
        try:
            PH.verify(stored_hash, password)
            if PH.check_needs_rehash(stored_hash):
                # rehash and update
                new_hash = PH.hash(password)
                cur.execute("UPDATE users SET password = ? WHERE email = ?", (new_hash, email))
                conn.commit()
            return True
        except Exception:
            return False


def create_session(email, days_valid=30):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if not row:
            raise ValueError("user not found")
        user_id = row[0]
        token = secrets.token_urlsafe(32)
        expires_at = int((datetime.datetime.utcnow() + datetime.timedelta(days=days_valid)).timestamp())
        cur.execute("INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
                    (user_id, token, expires_at))
        conn.commit()
        return token


def validate_session(token):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        now_ts = int(datetime.datetime.utcnow().timestamp())
        cur.execute(
            "SELECT users.email FROM sessions JOIN users ON sessions.user_id = users.id WHERE sessions.token = ? AND sessions.expires_at > ?",
            (token, now_ts),
        )
        row = cur.fetchone()
        return row[0] if row else None


if __name__ == "__main__":
    print("Running auth smoke test against", DB)
    ensure_db()

    test_email = "smoke@example.com"
    test_pwd = "Abcd1234!"

    # Clean up any previous test user
    with sqlite3.connect(DB) as c:
        cur = c.cursor()
        cur.execute("DELETE FROM sessions WHERE rowid > 0")
        cur.execute("DELETE FROM users WHERE email = ?", (test_email,))
        c.commit()

    print("Signing up user...")
    secret = signup(test_email, test_pwd)
    print("TOTP secret:", secret)

    # Simulate user reading current TOTP code from authenticator
    current_code = pyotp.TOTP(secret).now()
    print("Current TOTP code:", current_code)

    print("Verifying password...", verify_password(test_email, test_pwd))
    print("Verifying TOTP...", pyotp.TOTP(secret).verify(current_code))

    token = create_session(test_email)
    print("Created session token:", token)
    print("Validated session email:", validate_session(token))
    print("Smoke test complete.")

