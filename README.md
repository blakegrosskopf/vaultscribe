# VaultScribe — Local AI Meeting Summarizer (WIP)

**Status:** 🚧 Work in progress — repo scaffold coming soon. No code committed yet.

VaultScribe is a **privacy-first, on-device** meeting summarizer. Audio never leaves your machine, summaries are stored in an **encrypted local database**, and results remain unreadable until a **secure login with 2FA** is completed.

---

## Why
- **Privacy & Security:** Offline-first; no cloud by default.  
- **Control:** Your meetings, your machine, your keys.  
- **Clarity:** Action-oriented summaries and decisions in seconds.

## Planned Features (MVP)
- [ ] **Secure login** with email/password + **TOTP 2FA** (e.g., Authenticator app)  
- [ ] **Local transcription** (pluggable backend; e.g., whisper.cpp or Vosk)  
- [ ] **Local summarization** (pluggable small LLM; e.g., llama.cpp / GPT4All)  
- [ ] **Encrypted storage** (SQLite/SQLCipher) for transcripts & summaries  
- [ ] **Search & filter** across local summaries  
- [ ] **Export** redacted notes (TXT/Markdown)

## Architecture (initial sketch)
- **App:** Python (FastAPI + simple web UI) OR Electron/Next.js frontend talking to a local API  
- **Auth:** Local user store with salted hashes + TOTP secrets (hashed)  
- **DB:** Encrypted SQLite (SQLCipher)  
- **AI Pipeline:** Local STT → chunking → local LLM summary → action items/decisions → encrypted persist  
- **Encryption:** At-rest (DB) + in-process handling that keeps decrypted data in memory only after auth

> **No cloud calls** by default. Any optional connectors (e.g., calendar import) will be opt-in and clearly labeled.

## Security & Privacy Commitments
- 🔒 **Zero telemetry** by default  
- 🔑 **2FA required** for login  
- 🗄️ **Data stays local**; no third-party uploads  
- 🧾 **Auditability:** Log auth events locally (rotating, encrypted)

## Getting Started (coming soon)
- Prereqs: Python 3.11+, `pipx`, optional CUDA for local models  
- Quickstart script to bootstrap virtualenv, DB, and TOTP setup  
- Sample CLI and minimal web UI

## Roadmap
- **Milestone 1:** Project scaffold, auth + 2FA, encrypted DB init  
- **Milestone 2:** Local STT + basic summary pipeline  
- **Milestone 3:** UI, search, export; privacy hardening  
- **Milestone 4:** Packaging, docs, and demo

## Contributing
Early days! Open an issue with suggestions or privacy concerns. We’ll add contribution guidelines and a PR template once the scaffold lands.

## AI Code Assistant Disclosure
This project documents any usage of an AI code assistant (e.g., GitHub Copilot) in `docs/ai-assistant-usage.md` with files/commits and human review notes.

## License
TBD (likely MIT or Apache-2.0 once code is added).

---
*Name not final—feel free to rename `VaultScribe` in the header if this repo uses a different project name.*
