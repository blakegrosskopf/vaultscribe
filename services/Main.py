from pathlib import Path
import os
import re
import sqlite3

import bcrypt
import pyotp
import qrcode

from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDRaisedButton
from kivy.core.window import Window
from kivy.resources import resource_add_path, resource_find


# ---------------- Paths ----------------
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = (BASE_DIR / ".." / "assets").resolve()
UI_DIR = (BASE_DIR / ".." / "ui").resolve()
KV_PATH = UI_DIR / "main.kv"
QR_PATH = ASSETS_DIR / "totp_qr.png"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------- Helpers ----------------
def validateEmail(email: str) -> bool:
    pattern = (r"^(?!\.)(?!.*\.\.)[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
               r"@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")
    return re.match(pattern, email) is not None


def ensure_users_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            totp_secret TEXT
        )
        """
    )
    conn.commit()


# ---------------- Screens ----------------
class homeScreen(Screen):
    dialog = None
    rtrue = False
    pending_user_email = None  # set after password OK, before TOTP

    def show_popup(self, title, message):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(
            title=title,
            text=message,
            size_hint=(0.8, 0.4),
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: self.dialog.dismiss())],
        )
        self.dialog.open()

    def clear_fields(self):
        if self.rtrue:
            # remember-me keeps current text
            self.ids.user.text = self.ids.user.text
            self.ids.psswd.text = self.ids.psswd.text
        else:
            self.ids.user.text = ""
            self.ids.psswd.text = ""
        # clear TOTP UI contents
        if "totp_input" in self.ids:
            self.ids.totp_input.text = ""

    def remember(self):
        self.rtrue = not self.rtrue

    # Login step 1: password check
    def verify(self, user, psswd):
        database = "users.db"
        try:
            with sqlite3.connect(database) as conn:
                ensure_users_table(conn)
                cursor = conn.cursor()
                cursor.execute("SELECT password FROM users WHERE email = ?", (user,))
                row = cursor.fetchone()

                if not row:
                    self.show_popup("Error", "User not found.")
                    self.clear_fields()
                    return False

                stored_hash = row[0]
                # stored_hash may be str or bytes depending on insert
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode("utf-8")

                ok = bcrypt.checkpw(psswd.encode("utf-8"), stored_hash)
                if not ok:
                    self.show_popup("Error", "Invalid email or password.")
                    self.clear_fields()
                    return False

                # Password is correct → show TOTP step
                self.pending_user_email = user
                self.show_totp_box()
                self.show_popup("2FA Required", "Enter the 6-digit code from your authenticator.")
                return True

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")
            return False

    def show_totp_box(self):
        box = self.ids.totp_box
        box.opacity = 1
        box.disabled = False
        box.height = "90dp"

    # Login step 2: TOTP
    def verify_totp(self, code_text):
        if not self.pending_user_email:
            self.show_popup("Error", "No user in 2FA flow.")
            return

        database = "users.db"
        try:
            with sqlite3.connect(database) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT totp_secret FROM users WHERE email = ?",
                    (self.pending_user_email,),
                )
                row = cursor.fetchone()

                if not row or not row[0]:
                    self.show_popup("Error", "2FA not configured for this account.")
                    return

                secret = row[0]
                if pyotp.TOTP(secret).verify(code_text.strip(), valid_window=1):
                    self.show_popup("Success", "Login successful!")
                    self.clear_fields()
                    # hide TOTP box again
                    box = self.ids.totp_box
                    box.opacity = 0
                    box.disabled = True
                    box.height = 0
                    self.manager.current = "sScreen"
                else:
                    self.show_popup("Error", "Invalid 2FA code. Try again.")

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")


class signUp(Screen):
    dialog = None
    # temp state while enrolling TOTP before inserting into DB
    pending_email = None
    pending_pwd_hash = None
    pending_totp_secret = None

    def show_popup(self, title, message):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(
            title=title,
            text=message,
            size_hint=(0.8, 0.4),
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: self.dialog.dismiss())],
        )
        self.dialog.open()

    def clear_fields(self):
        if "username_input" in self.ids:
            self.ids.username_input.text = ""
        if "password_input" in self.ids:
            self.ids.password_input.text = ""
        if "totp_code_signup" in self.ids:
            self.ids.totp_code_signup.text = ""

    def create_user(self, username, password):
        # Validate email + password strength
        if not validateEmail(username):
            self.show_popup("Error", "Email is invalid.")
            return

        pattern = r'^(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*(),.?":{}|<>]).{8,}$'
        if not re.match(pattern, password):
            self.show_popup(
                "Error",
                "Password must be ≥8 chars and include a capital letter, a number, and a special char.",
            )
            return

        # Prepare bcrypt + TOTP
        try:
            pwd_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            secret = pyotp.random_base32()
            issuer = "VaultScribe"
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)

            # Save temp state until code verified
            self.pending_email = username
            self.pending_pwd_hash = pwd_hash
            self.pending_totp_secret = secret

            # Generate QR image
            img = qrcode.make(uri)
            img.save(QR_PATH)

            # Show TOTP enrollment UI (QR + code box)
            self.show_totp_enroll_ui()
            self.show_popup("Verify 2FA", "Scan the QR in your authenticator and enter the 6-digit code.")

        except Exception as e:
            self.show_popup("Error", f"Setup failed: {e}")

    def show_totp_enroll_ui(self):
        # hide normal inputs within the sign-up card
        for w in ("sBox", "cBox", "username_input", "password_input"):
            if w in self.ids:
                self.ids[w].opacity = 0
                if hasattr(self.ids[w], "disabled"):
                    self.ids[w].disabled = True

        # show QR + code input card
        enroll = self.ids.totp_enroll_box
        enroll.opacity = 1
        enroll.height = "300dp"
        if "totp_qr" in self.ids:
            self.ids.totp_qr.source = str(QR_PATH)
            self.ids.totp_qr.reload()

    def hide_totp_enroll_ui(self):
        enroll = self.ids.totp_enroll_box
        enroll.opacity = 0
        enroll.height = 0
        # show normal inputs again
        for w in ("sBox", "cBox", "username_input", "password_input"):
            if w in self.ids:
                self.ids[w].opacity = 1
                if hasattr(self.ids[w], "disabled"):
                    self.ids[w].disabled = False

    def complete_signup(self):
        # verify 6-digit code then insert user
        code = self.ids.totp_code_signup.text.strip() if "totp_code_signup" in self.ids else ""
        if not (self.pending_email and self.pending_pwd_hash and self.pending_totp_secret):
            self.show_popup("Error", "TOTP enrollment not initialized.")
            return

        if not pyotp.TOTP(self.pending_totp_secret).verify(code, valid_window=1):
            self.show_popup("Error", "Invalid 2FA code. Please try again.")
            return

        try:
            database = "users.db"
            with sqlite3.connect(database) as conn:
                ensure_users_table(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (email, password, totp_secret) VALUES (?, ?, ?)",
                    (self.pending_email, self.pending_pwd_hash, self.pending_totp_secret),
                )
                conn.commit()

            # cleanup temp + UI
            self.pending_email = None
            self.pending_pwd_hash = None
            self.pending_totp_secret = None
            self.clear_fields()
            self.hide_totp_enroll_ui()
            self.show_popup("Success", "Account created with 2FA.")
            self.manager.current = "home"

        except sqlite3.IntegrityError:
            self.show_popup("Error", "An account with this email already exists.")
        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")


class sScreen(Screen):
    pass


class changeScreen(Screen):
    # placeholder; wire a password-reset flow later
    dialog = None

    def show_popup(self, title, message):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(
            title=title,
            text=message,
            size_hint=(0.8, 0.4),
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: self.dialog.dismiss())],
        )
        self.dialog.open()


# ---------------- App ----------------
class MyApp(MDApp):
    def build(self):
        self.title = "VaultScribe"
        self._set_window_icon()

        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Indigo"

        sm = ScreenManager()
        sm.add_widget(homeScreen(name="home"))
        sm.add_widget(signUp(name="signUp"))
        sm.add_widget(sScreen(name="sScreen"))
        sm.add_widget(changeScreen(name="changeScreen"))
        return sm

    def _set_window_icon(self):
        """Set a re liable desktop window icon (ICO preferred on Windows)."""
        # Allow kivy to find assets by name
        resource_add_path(str(ASSETS_DIR))

        # Try ICO first, then PNG fallbacks
        for candidate in ("icon.ico", "icon_256.png", "icon.png"):
            path = resource_find(candidate)
            if path:
                try:
                    Window.set_icon(path)  # desktop window icon
                    self.icon = path       # app icon in some contexts/packagers
                    return
                except Exception:
                    pass  # try next option

    def take_shot(self, name="screen"):
        # Saves to ../assets/<name>.png
        path = ASSETS_DIR / f"{name}.png"
        Window.screenshot(name=str(path))


if __name__ == "__main__":
    Window.size = (360, 640)
    # Load KV then run
    Builder.load_file(str(KV_PATH))
    MyApp().run()
