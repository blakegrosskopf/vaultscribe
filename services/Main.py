from kivy.uix.boxlayout import BoxLayout
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDRaisedButton
from kivy.uix.label import Label

import os
import re
import sqlite3
import bcrypt
import pyotp
import qrcode
import os
from kivy.core.window import Window

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.abspath(os.path.join(HERE, "../assets"))
os.makedirs(ASSETS_DIR, exist_ok=True)

SVG_ICON = os.path.join(ASSETS_DIR, "vaultscribe-icon-square.svg")
PNG_ICON = os.path.join(ASSETS_DIR, "vaultscribe-icon-40.png")

def ensure_png_icon():
    """Convert SVG to a small PNG for Kivy Image if needed."""
    try:
        if os.path.exists(SVG_ICON) and not os.path.exists(PNG_ICON):
            import cairosvg
            # export a crisp 40x40 header icon
            cairosvg.svg2png(url=SVG_ICON, write_to=PNG_ICON, output_width=40, output_height=40)
    except Exception as e:
        print("SVG->PNG conversion failed:", e)



# ------------ Paths ------------
HERE = os.path.dirname(os.path.abspath(__file__))
# You load ../ui/main.kv, so assets are one directory up from this file too:
ASSETS_DIR = os.path.abspath(os.path.join(HERE, "../assets"))
QR_PATH = os.path.join(ASSETS_DIR, "totp_qr.png")

# ------------ Helpers ------------
def validateEmail(email: str) -> bool:
    pattern = (r"^(?!\.)(?!.*\.\.)[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
               r"@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")
    return re.match(pattern, email) is not None

def ensure_users_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            totp_secret TEXT
        )
    """)
    conn.commit()

# ------------ Screens ------------
class homeScreen(Screen):
    dialog = None
    rtrue = False
    pending_user_email = None  # set after password OK, before TOTP

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # UI helpers
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
        # clear TOTP UI
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
                cursor.execute('SELECT password FROM users WHERE email = ?', (user,))
                row = cursor.fetchone()

                if not row:
                    self.show_popup("Error", "User not found.")
                    self.clear_fields()
                    return False

                stored_hash = row[0]
                # bcrypt check
                ok = bcrypt.checkpw(psswd.encode("utf-8"), stored_hash.encode("utf-8") if isinstance(stored_hash, str) else stored_hash)
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
        # reveal the hidden TOTP area on login screen
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
                cursor.execute('SELECT totp_secret FROM users WHERE email = ?', (self.pending_user_email,))
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
                    self.manager.current = 'sScreen'
                else:
                    self.show_popup("Error", "Invalid 2FA code. Try again.")

        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")

    def on_kv_post(self, base_widget):
        """Load the VaultScribe SVG icon into the header slot."""
        try:
            icon_path = os.path.join(ASSETS_DIR, "vaultscribe-icon-square.svg")
            if os.path.exists(icon_path) and "logo_box" in self.ids:
                self.ids.logo_box.clear_widgets()
                svg = Svg(icon_path)
                svg.size_hint = (None, None)
                svg.size = (40, 40)
                self.ids.logo_box.add_widget(svg)
        except Exception as e:
            print("SVG load error:", e)

class signUp(Screen):
    dialog = None
    # temp state while enrolling TOTP before inserting into DB
    pending_email = None
    pending_pwd_hash = None
    pending_totp_secret = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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
        self.ids.username_input.text = ""
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
            self.show_popup("Error", "Password must be ≥8 chars and include a capital letter, a number, and a special char.")
            return

        # Prepare bcrypt + TOTP
        try:
            pwd_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode('utf-8')
            secret = pyotp.random_base32()
            issuer = "VaultScribe"
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)

            # Save temp state until code verified
            self.pending_email = username
            self.pending_pwd_hash = pwd_hash
            self.pending_totp_secret = secret

            # Generate QR image
            os.makedirs(ASSETS_DIR, exist_ok=True)
            img = qrcode.make(uri)
            img.save(QR_PATH)

            # Show TOTP enrollment UI (QR + code box)
            self.show_totp_enroll_ui()
            self.show_popup("Verify 2FA", "Scan the QR in your authenticator and enter the 6-digit code.")

        except Exception as e:
            self.show_popup("Error", f"Setup failed: {e}")

    def show_totp_enroll_ui(self):
        # hide normal inputs
        self.ids.sText.opacity = 0
        self.ids.sBox.opacity = 0
        self.ids.cBox.opacity = 0

        # show QR + code input
        enroll = self.ids.totp_enroll_box
        enroll.opacity = 1
        enroll.height = "300dp"
        self.ids.totp_qr.source = QR_PATH
        self.ids.totp_qr.reload()

    def hide_totp_enroll_ui(self):
        enroll = self.ids.totp_enroll_box
        enroll.opacity = 0
        enroll.height = 0
        # show normal inputs again
        self.ids.sText.opacity = 1
        self.ids.sBox.opacity = 1
        self.ids.cBox.opacity = 1

    def complete_signup(self):
        # verify 6-digit code then insert user
        code = self.ids.totp_code_signup.text.strip()
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
                cursor.execute("INSERT INTO users (email, password, totp_secret) VALUES (?, ?, ?)",
                               (self.pending_email, self.pending_pwd_hash, self.pending_totp_secret))
                conn.commit()

            # cleanup temp + UI
            self.pending_email = None
            self.pending_pwd_hash = None
            self.pending_totp_secret = None
            self.clear_fields()
            self.hide_totp_enroll_ui()
            self.show_popup("Success", "Account created with 2FA.")
            self.manager.current = 'home'

        except sqlite3.IntegrityError:
            self.show_popup("Error", "An account with this email already exists.")
        except sqlite3.Error as e:
            self.show_popup("Error", f"Database error: {e}")

class sScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class changeScreen(Screen):
    # placeholder; you can wire a password-reset flow later
    dialog = None
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

# ------------ App ------------
class MyApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Indigo"
        sm = ScreenManager()
        sm.add_widget(homeScreen(name='home'))
        sm.add_widget(signUp(name='signUp'))
        sm.add_widget(sScreen(name='sScreen'))
        sm.add_widget(changeScreen(name='changeScreen'))
        return sm
    def take_shot(self, name="screen"):
        # Saves to ../assets/<name>.png
        path = os.path.join(ASSETS_DIR, f"{name}.png")
        Window.screenshot(name=path)

if __name__ == "__main__":
    Window.size = (360, 640)
    ensure_png_icon()                     # <-- make the PNG if missing
    Builder.load_file("../ui/main.kv")    # then load the KV
    MyApp().run()
