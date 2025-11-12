import sqlite3
from pprint import pprint

DB = 'users.db'
with sqlite3.connect(DB) as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = cur.fetchall()
    print('users table columns:')
    pprint(cols)
    cur.execute("SELECT id, email, password, totp_secret FROM users")
    rows = cur.fetchall()
    print('\nuser rows:')
    for r in rows:
        print('---')
        print('id:', r[0])
        print('email:', r[1])
        pw = r[2]
        print('password repr type:', type(pw), 'len:', len(pw) if pw else 0)
        try:
            print('password preview:', (pw[:60] if isinstance(pw, str) else str(pw)[:60]))
        except Exception:
            print('password preview: <unprintable>')
        print('totp_secret:', r[3])

