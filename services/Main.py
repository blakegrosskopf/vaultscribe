from pathlib import Path
import re
import sqlite3
import secrets
import datetime
import threading
import traceback
import os

from argon2 import PasswordHasher, exceptions as argon2_exceptions
from argon2.low_level import Type
import pyotp
import qrcode

from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDRaisedButton
from kivy.core.window import Window
from kivy.resources import resource_add_path, resource_find
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.image import Image

from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

# AI backend
from services.backend_ai.Ai_API import AISummarizerTranscriber

# ---------------- Paths ----------------
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
ASSETS_DIR = (ROOT_DIR / "assets").resolve()
UI_DIR = (ROOT_DIR / "ui").resolve()
BACKEND_DIR = (ROOT_DIR / "services" / "backend_ai").resolve()

KV_PATH = UI_DIR / "main.kv"
QR_PATH = ASSETS_DIR / "totp_qr.png"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = BACKEND_DIR / "ffmpeg-master-latest-win64-gpl-shared" / "bin"
os.environ["PATH"] = f"{FFMPEG_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
# Make assets available to KV and Kivy resource lookup immediately
try:
    resource_add_path(str(ASSETS_DIR))
except Exception:
    pass

# Database filename used by the app
DB_PATH = str(ROOT_DIR / "users.db")

# ---------------- Argon2id Hasher ----------------
ph = PasswordHasher(type=Type.ID)  # argon2id


# ---------------- Helpers ----------------
def validateEmail(email: str) -> bool:
    pattern = (r"^(?!\.)(?!.*\.\.)[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
               r"@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")
    return re.match(pattern, email) is not None


def ensure_db_tables(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
        """
    )
    try:
        cur.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cur.fetchall()]
        if "totp_secret" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
    except sqlite3.Error:
        pass

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT UNIQUE,
            expires_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()


def create_session(conn: sqlite3.Connection, email: str, days_valid: int = 30) -> str:
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    if not row:
        raise ValueError("User not found for session creation.")
    user_id = row[0]
    token = secrets.token_urlsafe(32)
    expires_at = int((datetime.datetime.utcnow() + datetime.timedelta(days=days_valid)).timestamp())
    cur.execute(
        "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at),
    )
    conn.commit()
    return token


def validate_session(conn: sqlite3.Connection, token: str):
    cur = conn.cursor()
    now_ts = int(datetime.datetime.utcnow().timestamp())
    cur.execute(
        """
        SELECT users.email FROM sessions
        JOIN users ON sessions.user_id = users.id
        WHERE sessions.token = ? AND sessions.expires_at > ?
        """,
        (token, now_ts),
    )
    row = cur.fetchone()
    return row[0] if row else None


def delete_session(conn: sqlite3.Connection, token: str):
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


# ---------------- Screens ----------------
class homeScreen(Screen):
    dialog = None
    totp_modal = None
    rtrue = False
    pending_user_email = None
    current_session_token = None

    def __init__(self, **kwargs):
        super(homeScreen, self).__init__(**kwargs)
        self.totp_modal = None

    def build_totp_modal(self):
        modal = ModalView(
            size_hint=(0.95, None),
            height="360dp",
            background_color=[0, 0, 0, 0.5],
            auto_dismiss=False,
        )

        content = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height="240dp",
            padding="24dp",
            spacing="12dp",
            radius=[18],
            md_bg_color=[0.16, 0.17, 0.3, 1],
            elevation=4,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )

        title = MDLabel(
            text="2FA Required",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 1],
            font_size="20dp",
            bold=True,
            size_hint_y=None,
            height="30dp",
            halign="left",
        )
        content.add_widget(title)

        subtitle = MDLabel(
            text="Enter the 6-digit code from your authenticator app",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="16dp",
            size_hint_y=None,
            height="50dp",
            halign="left",
        )
        content.add_widget(subtitle)

        input_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            spacing="12dp",
            padding=[0, "12dp", 0, 0],
        )

        self.modal_totp_input = MDTextField(
            hint_text="6-digit code",
            mode="rectangle",
            size_hint_x=0.6,
            font_size="18dp",
            max_text_length=6,
            helper_text="Enter code from authenticator",
            helper_text_mode="on_error",
        )
        input_box.add_widget(self.modal_totp_input)

        verify_btn = MDRaisedButton(
            text="Verify",
            font_size="16dp",
            size_hint_x=0.4,
            on_release=lambda x: self.verify_totp(self.modal_totp_input.text),
        )
        input_box.add_widget(verify_btn)

        content.add_widget(input_box)
        modal.add_widget(content)
        return modal

    def show_popup(self, title, message):
        if self.dialog:
            try:
                self.dialog.dismiss()
            except Exception:
                pass

        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
            size_hint_y=None,
            height="120dp",
        )

        msg_label = MDLabel(
            text=message,
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="60dp",
            halign="left",
            valign="top",
        )
        content.add_widget(msg_label)

        ok_btn = MDRaisedButton(
            text="OK",
            size_hint_x=1,
            on_release=lambda x: self.dialog.dismiss(),
        )
        content.add_widget(ok_btn)

        self.dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            size_hint=(0.8, None),
            height="200dp",
        )
        self.dialog.open()

    def clear_fields(self):
        if self.rtrue:
            self.ids.user.text = self.ids.user.text
            self.ids.psswd.text = self.ids.psswd.text
        else:
            self.ids.user.text = ""
            self.ids.psswd.text = ""
        try:
            self.modal_totp_input.text = ""
        except Exception:
            pass

    def remember(self):
        self.rtrue = not self.rtrue

    def verify(self, user, psswd):
        database = DB_PATH
        try:
            with sqlite3.connect(database) as conn:
                ensure_db_tables(conn)
                cursor = conn.cursor()
                cursor.execute("SELECT password FROM users WHERE email = ?", (user,))
                row = cursor.fetchone()

                if not row:
                    self.show_popup("Error", "User not found.")
                    self.clear_fields()
                    return False

                stored_hash = row[0]
                if isinstance(stored_hash, bytes):
                    try:
                        stored_hash = stored_hash.decode("utf-8")
                    except Exception:
                        stored_hash = str(stored_hash)

                verified = False
                used_legacy = False
                try:
                    try:
                        prefix = stored_hash[:16]
                    except Exception:
                        prefix = str(type(stored_hash))
                    print(
                        f"[auth] Argon2 verify: stored_hash_type={type(stored_hash)}, prefix={prefix}"
                    )
                    ph.verify(stored_hash, psswd)
                    verified = True
                    if ph.check_needs_rehash(stored_hash):
                        new_hash = ph.hash(psswd)
                        cursor.execute(
                            "UPDATE users SET password = ? WHERE email = ?",
                            (new_hash, user),
                        )
                        conn.commit()
                except argon2_exceptions.VerifyMismatchError:
                    self.show_popup("Error", "Invalid email or password.")
                    self.clear_fields()
                    return False
                except argon2_exceptions.InvalidHash:
                    used_legacy = True
                except Exception:
                    print("[auth] Unexpected Argon2 exception:")
                    traceback.print_exc()
                    used_legacy = True

                if not verified and used_legacy:
                    try:
                        if isinstance(stored_hash, str) and stored_hash.startswith("$2"):
                            try:
                                import bcrypt as _bcrypt
                            except Exception:
                                print("bcrypt not available for legacy hash verification")
                                traceback.print_exc()
                                self.show_popup(
                                    "Error", "Legacy password verifier unavailable."
                                )
                                return False
                            try:
                                ok = _bcrypt.checkpw(
                                    psswd.encode("utf-8"),
                                    stored_hash.encode("utf-8"),
                                )
                                if ok:
                                    verified = True
                                    new_hash = ph.hash(psswd)
                                    cursor.execute(
                                        "UPDATE users SET password = ? WHERE email = ?",
                                        (new_hash, user),
                                    )
                                    conn.commit()
                                else:
                                    self.show_popup("Error", "Invalid email or password.")
                                    self.clear_fields()
                                    return False
                            except Exception:
                                print("bcrypt verification error:")
                                traceback.print_exc()
                                self.show_popup(
                                    "Error",
                                    "Legacy bcrypt verify failed (see console).",
                                )
                                return False
                        else:
                            if stored_hash == psswd:
                                verified = True
                                new_hash = ph.hash(psswd)
                                cursor.execute(
                                    "UPDATE users SET password = ? WHERE email = ?",
                                    (new_hash, user),
                                )
                                conn.commit()
                            else:
                                self.show_popup("Error", "Invalid email or password.")
                                self.clear_fields()
                                return False
                    except Exception:
                        print("[auth] legacy fallback exception:")
                        traceback.print_exc()
                        try:
                            self.show_popup(
                                "Error",
                                "Authentication failed. If this continues, check logs.",
                            )
                        except Exception:
                            pass
                        return False

                self.pending_user_email = user
                self.show_totp_box()
                self.show_popup(
                    "2FA Required", "Enter the 6-digit code from your authenticator."
                )
                return True

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")
            return False

    def show_totp_box(self):
        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None

        self.totp_modal = self.build_totp_modal()
        try:
            self.modal_totp_input.text = ""
            self.modal_totp_input.focus = True
        except Exception:
            pass
        self.totp_modal.open()

    def hide_totp_box(self):
        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None
            try:
                self.modal_totp_input.text = ""
            except Exception:
                pass

    def verify_totp(self, code_text):
        if not self.pending_user_email:
            self.show_popup("Error", "No user in 2FA flow.")
            return

        database = DB_PATH
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
                    token = create_session(conn, self.pending_user_email)
                    self.current_session_token = token
                    try:
                        MDApp.get_running_app().current_session_token = token
                    except Exception:
                        pass
                    self.show_popup(
                        "Success", f"Login successful!\nSession token: {token}"
                    )
                    self.clear_fields()
                    self.hide_totp_box()
                    self.manager.current = "sScreen"
                else:
                    self.show_popup("Error", "Invalid 2FA code. Try again.")

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")


class signUp(Screen):
    dialog = None
    totp_modal = None
    pending_email = None
    pending_pwd_hash = None
    pending_totp_secret = None

    def __init__(self, **kwargs):
        super(signUp, self).__init__(**kwargs)
        self.totp_modal = None

    def build_totp_modal(self):
        modal = ModalView(
            size_hint=(0.95, None),
            height="640dp",
            background_color=[0, 0, 0, 0.5],
            auto_dismiss=False,
        )

        content = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height="600dp",
            padding="24dp",
            spacing="16dp",
            radius=[18],
            md_bg_color=[0.16, 0.17, 0.3, 1],
            elevation=4,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )

        title = MDLabel(
            text="Set Up Two-Factor Authentication",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 1],
            font_size="20dp",
            bold=True,
            size_hint_y=None,
            height="30dp",
            halign="left",
        )
        content.add_widget(title)

        subtitle = MDLabel(
            text="1. Open Google/Microsoft Authenticator on your phone\n"
            "2. Scan this QR code to add your account\n"
            "3. Enter the 6-digit code shown in the app",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="60dp",
            halign="left",
        )
        content.add_widget(subtitle)

        self.modal_qr_image = Image(
            source=str(QR_PATH),
            size_hint=(None, None),
            size=("240dp", "240dp"),
            pos_hint={"center_x": 0.5},
            allow_stretch=True,
            keep_ratio=True,
        )
        content.add_widget(self.modal_qr_image)

        input_layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="140dp",
            spacing="12dp",
            padding=[0, "12dp", 0, 0],
        )

        self.modal_totp_input = MDTextField(
            hint_text="6-digit code",
            mode="rectangle",
            size_hint=(None, None),
            size=("200dp", "56dp"),
            pos_hint={"center_x": 0.5},
            font_size="18dp",
            max_text_length=6,
            helper_text="Enter code from authenticator",
            helper_text_mode="on_error",
        )
        input_layout.add_widget(self.modal_totp_input)

        button_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="12dp",
            padding=[0, "12dp", 0, 0],
        )

        verify_btn = MDRaisedButton(
            text="Verify & Create Account",
            font_size="14dp",
            size_hint_x=0.7,
            on_release=lambda x: self.complete_signup(),
        )
        button_box.add_widget(verify_btn)

        cancel_btn = MDRaisedButton(
            text="Cancel",
            font_size="14dp",
            size_hint_x=0.3,
            on_release=lambda x: self.hide_totp_enroll_ui(),
        )
        button_box.add_widget(cancel_btn)

        input_layout.add_widget(button_box)
        content.add_widget(input_layout)
        modal.add_widget(content)
        return modal

    def show_popup(self, title, message):
        if self.dialog:
            try:
                self.dialog.dismiss()
            except Exception:
                pass

        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
            size_hint_y=None,
            height="120dp",
        )

        msg_label = MDLabel(
            text=message,
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="60dp",
            halign="left",
            valign="top",
        )
        content.add_widget(msg_label)

        ok_btn = MDRaisedButton(
            text="OK",
            size_hint_x=1,
            on_release=lambda x: self.dialog.dismiss(),
        )
        content.add_widget(ok_btn)

        self.dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            size_hint=(0.8, None),
            height="200dp",
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
        if not validateEmail(username):
            self.show_popup("Error", "Email is invalid.")
            return

        pattern = r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(pattern, password):
            self.show_popup(
                "Error",
                "Password must be ≥8 chars and include a capital letter, a number, and a special char.",
            )
            return

        try:
            pwd_hash = ph.hash(password)
            secret = pyotp.random_base32()
            issuer = "VaultScribe"
            uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=username, issuer_name=issuer
            )

            self.pending_email = username
            self.pending_pwd_hash = pwd_hash
            self.pending_totp_secret = secret

            img = qrcode.make(uri)
            img.save(QR_PATH)

            self.show_totp_enroll_ui()
            self.show_popup(
                "Verify 2FA",
                "Scan the QR in your authenticator and enter the 6-digit code.",
            )

        except Exception as e:
            self.show_popup("Error", f"Setup failed: {e}")

    def show_totp_enroll_ui(self):
        for w in ("sBox", "cBox", "username_input", "password_input"):
            if w in self.ids:
                self.ids[w].opacity = 0
                if hasattr(self.ids[w], "disabled"):
                    self.ids[w].disabled = True

        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None

        self.totp_modal = self.build_totp_modal()

        try:
            self.modal_qr_image.source = str(QR_PATH)
            self.modal_qr_image.reload()
        except Exception:
            pass

        try:
            self.modal_totp_input.text = ""
            self.modal_totp_input.focus = True
        except Exception:
            pass
        self.totp_modal.open()

    def hide_totp_enroll_ui(self):
        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None

        for w in ("sBox", "cBox", "username_input", "password_input"):
            if w in self.ids:
                self.ids[w].opacity = 1
                if hasattr(self.ids[w], "disabled"):
                    self.ids[w].disabled = False

        self.pending_email = None
        self.pending_pwd_hash = None
        self.pending_totp_secret = None

    def complete_signup(self):
        code = (
            self.modal_totp_input.text.strip()
            if hasattr(self, "modal_totp_input")
            else ""
        )
        if not (
            self.pending_email and self.pending_pwd_hash and self.pending_totp_secret
        ):
            self.show_popup("Error", "TOTP enrollment not initialized.")
            return

        if not pyotp.TOTP(self.pending_totp_secret).verify(code, valid_window=1):
            self.show_popup("Error", "Invalid 2FA code. Please try again.")
            return

        try:
            database = DB_PATH
            with sqlite3.connect(database) as conn:
                ensure_db_tables(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (email, password, totp_secret) VALUES (?, ?, ?)",
                    (
                        self.pending_email,
                        self.pending_pwd_hash,
                        self.pending_totp_secret,
                    ),
                )
                conn.commit()

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
    dialog = None

    def show_popup(self, title, message):
        if self.dialog:
            try:
                self.dialog.dismiss()
            except Exception:
                pass

        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
            size_hint_y=None,
            height="120dp",
        )

        msg_label = MDLabel(
            text=message,
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="60dp",
            halign="left",
            valign="top",
        )
        content.add_widget(msg_label)

        ok_btn = MDRaisedButton(
            text="OK",
            size_hint_x=1,
            on_release=lambda x: self.dialog.dismiss(),
        )
        content.add_widget(ok_btn)

        self.dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            size_hint=(0.8, None),
            height="200dp",
        )
        self.dialog.open()

    def logout(self):
        token = None
        try:
            token = MDApp.get_running_app().current_session_token
        except Exception:
            token = None

        if token:
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    delete_session(conn, token)
            except Exception:
                pass

        try:
            MDApp.get_running_app().current_session_token = None
        except Exception:
            pass

        self.show_popup("Signed out", "You have been logged out.")
        try:
            self.manager.current = "home"
        except Exception:
            pass


class changeScreen(Screen):
    dialog = None
    totp_modal = None
    pending_reset_email = None
    pending_new_password = None

    def __init__(self, **kwargs):
        super(changeScreen, self).__init__(**kwargs)
        self.totp_modal = None

    def build_totp_modal(self):
        modal = ModalView(
            size_hint=(0.95, None),
            height="360dp",
            background_color=[0, 0, 0, 0.5],
            auto_dismiss=False,
        )

        content = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height="240dp",
            padding="24dp",
            spacing="12dp",
            radius=[18],
            md_bg_color=[0.16, 0.17, 0.3, 1],
            elevation=4,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )

        title = MDLabel(
            text="Verify Your Identity",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 1],
            font_size="20dp",
            bold=True,
            size_hint_y=None,
            height="30dp",
            halign="left",
        )
        content.add_widget(title)

        subtitle = MDLabel(
            text="Enter the 6-digit code from your authenticator app",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="16dp",
            size_hint_y=None,
            height="50dp",
            halign="left",
        )
        content.add_widget(subtitle)

        input_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            spacing="12dp",
            padding=[0, "12dp", 0, 0],
        )

        self.modal_totp_input = MDTextField(
            hint_text="6-digit code",
            mode="rectangle",
            size_hint_x=0.6,
            font_size="18dp",
            max_text_length=6,
            helper_text="Enter code from authenticator",
            helper_text_mode="on_error",
        )
        input_box.add_widget(self.modal_totp_input)

        verify_btn = MDRaisedButton(
            text="Verify",
            font_size="16dp",
            size_hint_x=0.4,
            on_release=lambda x: self.verify_2fa_for_reset(
                self.modal_totp_input.text
            ),
        )
        input_box.add_widget(verify_btn)

        content.add_widget(input_box)
        modal.add_widget(content)
        return modal

    def build_password_modal(self):
        modal = ModalView(
            size_hint=(0.95, None),
            height="420dp",
            background_color=[0, 0, 0, 0.5],
            auto_dismiss=False,
        )

        content = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height="380dp",
            padding="24dp",
            spacing="12dp",
            radius=[18],
            md_bg_color=[0.16, 0.17, 0.3, 1],
            elevation=4,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )

        title = MDLabel(
            text="Reset Password",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 1],
            font_size="20dp",
            bold=True,
            size_hint_y=None,
            height="30dp",
            halign="left",
        )
        content.add_widget(title)

        subtitle = MDLabel(
            text="Enter a new password (8+ chars, capital letter, number, special char)",
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="50dp",
            halign="left",
        )
        content.add_widget(subtitle)

        self.modal_password_input = MDTextField(
            hint_text="New password",
            mode="rectangle",
            password=True,
            size_hint=(None, None),
            size=("280dp", "56dp"),
            pos_hint={"center_x": 0.5},
            font_size="14dp",
        )
        content.add_widget(self.modal_password_input)

        self.modal_confirm_input = MDTextField(
            hint_text="Confirm password",
            mode="rectangle",
            password=True,
            size_hint=(None, None),
            size=("280dp", "56dp"),
            pos_hint={"center_x": 0.5},
            font_size="14dp",
        )
        content.add_widget(self.modal_confirm_input)

        button_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="12dp",
            padding=[0, "12dp", 0, 0],
        )

        reset_btn = MDRaisedButton(
            text="Reset Password",
            font_size="14dp",
            size_hint_x=0.6,
            on_release=lambda x: self.complete_password_reset(
                self.modal_password_input.text,
                self.modal_confirm_input.text,
            ),
        )
        button_box.add_widget(reset_btn)

        cancel_btn = MDRaisedButton(
            text="Cancel",
            font_size="14dp",
            size_hint_x=0.4,
            on_release=lambda x: self.hide_password_modal(),
        )
        button_box.add_widget(cancel_btn)

        content.add_widget(button_box)
        modal.add_widget(content)
        return modal

    def show_popup(self, title, message):
        if self.dialog:
            try:
                self.dialog.dismiss()
            except Exception:
                pass

        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
            size_hint_y=None,
            height="120dp",
        )

        msg_label = MDLabel(
            text=message,
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="60dp",
            halign="left",
            valign="top",
        )
        content.add_widget(msg_label)

        ok_btn = MDRaisedButton(
            text="OK",
            size_hint_x=1,
            on_release=lambda x: self.dialog.dismiss(),
        )
        content.add_widget(ok_btn)

        self.dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            size_hint=(0.8, None),
            height="200dp",
        )
        self.dialog.open()

    def clear_fields(self):
        if "email" in self.ids:
            self.ids.email.text = ""

    def start_password_reset(self, email):
        if not email.strip():
            self.show_popup("Error", "Please enter an email address.")
            return

        if not validateEmail(email):
            self.show_popup("Error", "Please enter a valid email address.")
            return

        database = DB_PATH
        try:
            with sqlite3.connect(database) as conn:
                ensure_db_tables(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT totp_secret FROM users WHERE email = ?",
                    (email,),
                )
                row = cursor.fetchone()

                if not row:
                    self.show_popup("Error", "No account found with this email.")
                    return

                if not row[0]:
                    self.show_popup(
                        "Error", "This account does not have 2FA configured."
                    )
                    return

                self.pending_reset_email = email
                self.show_totp_modal_for_reset()
                self.show_popup(
                    "2FA Verification",
                    "Enter the 6-digit code from your authenticator.",
                )

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")

    def show_totp_modal_for_reset(self):
        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None

        self.totp_modal = self.build_totp_modal()
        try:
            self.modal_totp_input.text = ""
            self.modal_totp_input.focus = True
        except Exception:
            pass
        self.totp_modal.open()

    def hide_totp_modal(self):
        if self.totp_modal:
            try:
                self.totp_modal.dismiss()
            except Exception:
                pass
            self.totp_modal = None

    def verify_2fa_for_reset(self, code_text):
        if not self.pending_reset_email:
            self.show_popup("Error", "No email in reset flow.")
            return

        database = DB_PATH
        try:
            with sqlite3.connect(database) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT totp_secret FROM users WHERE email = ?",
                    (self.pending_reset_email,),
                )
                row = cursor.fetchone()

                if not row or not row[0]:
                    self.show_popup("Error", "2FA not configured for this account.")
                    return

                secret = row[0]
                if pyotp.TOTP(secret).verify(code_text.strip(), valid_window=1):
                    self.hide_totp_modal()
                    self.show_password_modal()
                else:
                    self.show_popup("Error", "Invalid 2FA code. Try again.")

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")

    def show_password_modal(self):
        password_modal = self.build_password_modal()
        try:
            self.modal_password_input.text = ""
            self.modal_confirm_input.text = ""
            self.modal_password_input.focus = True
        except Exception:
            pass
        password_modal.open()
        self._current_password_modal = password_modal

    def hide_password_modal(self):
        if hasattr(self, "_current_password_modal"):
            try:
                self._current_password_modal.dismiss()
            except Exception:
                pass
            self._current_password_modal = None

    def complete_password_reset(self, new_pwd, confirm_pwd):
        if not new_pwd or not confirm_pwd:
            self.show_popup("Error", "Please enter and confirm your password.")
            return

        if new_pwd != confirm_pwd:
            self.show_popup("Error", "Passwords do not match.")
            return

        pattern = r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(pattern, new_pwd):
            self.show_popup(
                "Error",
                "Password must be ≥8 chars and include a capital letter, a number, and a special char.",
            )
            return

        database = DB_PATH
        try:
            new_hash = ph.hash(new_pwd)
            with sqlite3.connect(database) as conn:
                ensure_db_tables(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET password = ? WHERE email = ?",
                    (new_hash, self.pending_reset_email),
                )
                conn.commit()

            self.pending_reset_email = None
            self.pending_new_password = None
            self.clear_fields()
            self.hide_password_modal()
            self.show_popup(
                "Success",
                "Password reset successfully! You can now login with your new password.",
            )
            self.manager.current = "home"

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")


# --------- New AI-related screens ---------
class TranscribeScreen(Screen):
    dialog = None
    working = False

    def show_popup(self, title, message):
        if self.dialog:
            try:
                self.dialog.dismiss()
            except Exception:
                pass

        from kivymd.uix.boxlayout import MDBoxLayout

        content = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="12dp",
            size_hint_y=None,
            height="160dp",
        )

        msg_label = MDLabel(
            text=message,
            theme_text_color="Custom",
            text_color=[1, 1, 1, 0.87],
            font_size="14dp",
            size_hint_y=None,
            height="80dp",
            halign="left",
            valign="top",
        )
        content.add_widget(msg_label)

        ok_btn = MDRaisedButton(
            text="OK",
            size_hint_x=1,
            on_release=lambda x: self.dialog.dismiss(),
        )
        content.add_widget(ok_btn)

        self.dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            size_hint=(0.9, None),
            height="220dp",
        )
        self.dialog.open()

    def start_transcription(self, audio_path_text: str):
        if self.working:
            return

        app = MDApp.get_running_app()
        if not getattr(app, "ai", None):
            self.show_popup("AI Error", "AI backend is not initialized.")
            return

        audio_path = audio_path_text.strip() or str(
            BACKEND_DIR / "transcription_test.wav"
        )

        if not Path(audio_path).is_file():
            self.show_popup("File Error", f"Audio file not found:\n{audio_path}")
            return

        self.working = True
        self.ids.transcribe_button.text = "Working..."
        self.ids.transcribe_button.disabled = True
        self.ids.summary_output.text = ""

        def worker():
            try:
                transcript = app.ai.transcribe(audio_path)
                summary = app.ai.summarize(transcript)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt: self.show_popup("AI Error", f"{e}")
                )
                Clock.schedule_once(lambda dt: self._reset_button_state())
                return

            def update_ui(dt):
                # show summary in the text box
                self.ids.summary_output.text = summary
                # persist in app history for storage screen
                app.meeting_history.append(
                    {
                        "audio_path": audio_path,
                        "transcript": transcript,
                        "summary": summary,
                        "timestamp": datetime.datetime.utcnow().isoformat(
                            timespec="seconds"
                        ),
                    }
                )
                self._reset_button_state()

            Clock.schedule_once(update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_button_state(self):
        self.working = False
        self.ids.transcribe_button.text = "Transcribe"
        self.ids.transcribe_button.disabled = False


class StorageScreen(Screen):
    def on_pre_enter(self, *args):
        self.refresh_history()

    def refresh_history(self):
        app = MDApp.get_running_app()
        items = app.meeting_history
        if not items:
            self.ids.storage_label.text = "No stored transcriptions yet."
            return

        lines = []
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"[b]#{idx}[/b]  ({item.get('timestamp','')})\n"
                f"[i]{item.get('audio_path','')}[/i]\n"
                f"{item.get('summary','')}\n"
                "----------------------------------------"
            )
        self.ids.storage_label.text = "\n".join(lines)


class SettingsScreen(Screen):
    pass


class HelpScreen(Screen):
    pass


# ---------------- App ----------------
class MyApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_session_token = None
        self.ai = None
        self.meeting_history = []

    def build(self):
        self.title = "VaultScribe"

        try:
            resource_add_path(str(ASSETS_DIR))
        except Exception:
            pass

        try:
            Builder.load_file(str(KV_PATH))
        except Exception:
            pass

        self._set_window_icon()

        try:
            with sqlite3.connect(DB_PATH) as conn:
                ensure_db_tables(conn)
        except sqlite3.Error:
            pass

        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Indigo"

        sm = ScreenManager()
        sm.add_widget(homeScreen(name="home"))
        sm.add_widget(sScreen(name="sScreen"))
        sm.add_widget(signUp(name="signUp"))
        sm.add_widget(changeScreen(name="changeScreen"))
        sm.add_widget(TranscribeScreen(name="transcribeScreen"))
        sm.add_widget(StorageScreen(name="storageScreen"))
        sm.add_widget(SettingsScreen(name="settingsScreen"))
        sm.add_widget(HelpScreen(name="helpScreen"))
        return sm

    def on_start(self):
        # init AI backend
        try:
            # Optionally override key from env:
            # api_key = os.getenv("OPENROUTER_API_KEY")
            # self.ai = AISummarizerTranscriber(
            #     model_dir=str(BACKEND_DIR / "whisper"),
            #     openrouter_api_key=api_key,
            # )
            self.ai = AISummarizerTranscriber(
                model_dir=str(BACKEND_DIR / "whisper")
            )
            print("[ai] AISummarizerTranscriber initialized")
        except Exception as e:
            print("[ai] Failed to initialize backend:", e)
            self.ai = None

    def _set_window_icon(self):
        resource_add_path(str(ASSETS_DIR))

        for candidate in ("icon.ico", "icon_256.png", "icon.png"):
            path = resource_find(candidate)
            if path:
                try:
                    Window.set_icon(path)
                    self.icon = path
                    return
                except Exception:
                    pass

    def take_shot(self, name="screen"):
        path = ASSETS_DIR / f"{name}.png"
        Window.screenshot(name=str(path))


if __name__ == "__main__":
    Window.size = (360, 640)
    MyApp().run()
