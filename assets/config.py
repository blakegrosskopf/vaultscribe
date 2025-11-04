from dotenv import load_dotenv
import os
load_dotenv()
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SMTP_USER")
SENDER_PASSWORD = os.getenv("SMTP_PASS")
DB_PATH = os.getenv("DB_PATH", "vaultscribe.db")
DB_KEY = os.getenv("DB_KEY", "dev-only-change-me")  # for SQLCipher