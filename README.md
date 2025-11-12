# 🔐 LoginSystemDesktop

**LoginSystemDesktop** is a secure desktop authentication system built in **Python (Kivy/KivyMD)**.  
It’s designed as a **foundational security module** for my larger project, **VaultScribe**, an upcoming **AI-powered meeting summarizer** that operates *entirely locally* — ensuring **data privacy, encryption, and zero network exposure**.

---

## 🧠 Project Overview

This application serves as a **local login and identity management interface** with a focus on **real-world cybersecurity best practices**.

- Implements **Argon2id hashing** for password storage — a modern, memory-hard algorithm resistant to brute-force and GPU attacks.
- Integrates **TOTP (Time-Based One-Time Password)** using **Google/Microsoft Authenticator** for **two-factor authentication (2FA)**.
- Uses **SQLite** for secure local credential storage — never transmitting data across networks.
- Supports **session management and expiry**, ensuring user tokens are both random and time-limited.
- Includes **modular UI design** for scalability into future local applications.

---

## 🛡️ Security Features

| Feature | Description |
|----------|-------------|
| **Argon2id Password Hashing** | Uses industry-standard Argon2id for secure password hashing and optional legacy migration for older bcrypt/plaintext entries. |
| **Two-Factor Authentication (2FA)** | Enforces TOTP 6-digit verification codes synced with authenticator apps. |
| **Local Database Encryption Surface** | Operates on a local `SQLite` file — ensuring no credentials or session data are sent over the internet. |
| **Session Tokens** | Securely generated with Python’s `secrets` library; automatically expired after 30 days. |
| **Password Strength Enforcement** | Requires ≥8 characters, one uppercase letter, one number, and one special character. |
| **Secure UI Isolation** | All credential handling occurs through local Kivy/KivyMD UI components — no browser-based attack surface. |

---

## 🧩 Tech Stack

- **Language:** Python 3.x  
- **UI Framework:** Kivy / KivyMD  
- **Database:** SQLite  
- **Security Libraries:**  
  - `argon2-cffi` (Argon2id hashing)  
  - `pyotp` (TOTP 2FA)  
  - `qrcode` (QR code generation)  
  - `secrets` (session tokens)  

---

## 🧱 Future Integration — VaultScribe

This project is the **login and security front-end** for **VaultScribe**, an AI-powered local application designed for **lawyers, doctors, and professionals** who handle sensitive information.

**VaultScribe** will:
- Summarize meetings and transcriptions using **on-device AI**.
- Store and encrypt data locally.
- Never send or expose files to external servers or APIs.
- Provide **enterprise-level security** for small and medium businesses.

> ⚙️ LoginSystemDesktop ensures that when VaultScribe launches, it inherits an already secure and privacy-focused authentication base.

---

## 🖥️ How It Works

1. **Sign Up**  
   - User creates an account with a strong password.  
   - App generates a TOTP secret and shows a QR code to link to an authenticator app.

2. **Login**  
   - User enters credentials.  
   - App verifies Argon2id hash and prompts for 2FA code.  
   - On success, a session token is generated and saved securely.

3. **Password Reset**  
   - Requires valid 2FA verification.  
   - Enforces same password-strength rules before updating Argon2id hash.

---
