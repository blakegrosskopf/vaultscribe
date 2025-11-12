from argon2 import PasswordHasher
import sqlite3

DB='users.db'
email='smoke@example.com'
ph = PasswordHasher()
with sqlite3.connect(DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    if not row:
        print('no user')
    else:
        stored = row[0]
        print('stored type', type(stored))
        try:
            ok = ph.verify(stored, 'Abcd1234!')
            print('ph.verify returned:', ok)
        except Exception as e:
            print('verify raised:', type(e), e)
            import traceback; traceback.print_exc()

