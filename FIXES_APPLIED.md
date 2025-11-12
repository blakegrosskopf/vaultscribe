# MFA Login App - Fixes Applied

## Summary of Issues Fixed

### 1. **Missing KivyMD Imports** ✅
**Problem**: The code referenced `MDCard`, `MDLabel`, and `MDTextField` but they were not imported, causing `NameError: name 'MDCard' is not defined` at runtime.

**Solution**: Added the following imports to `services/Main.py`:
```python
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivy.uix.image import Image
```

### 2. **Modal Reparenting Error** ✅
**Problem**: When trying to open a modal that was already added to a parent, Kivy raised: `kivy.uix.widget.WidgetException: Cannot add ModalOverlay to window, it already has a parent`

**Solution**: Refactored modal creation to build a fresh `ModalView` on-demand instead of creating it once in `__init__`:
- Removed persistent `create_totp_modal()` from `__init__`
- Added `build_totp_modal()` methods to both `homeScreen` and `signUp` classes
- Each call to `show_totp_box()` and `show_totp_enroll_ui()` now builds and opens a fresh modal instance
- This avoids reparenting issues and ensures clean z-ordering

### 3. **Database Schema Missing totp_secret Column** ✅
**Problem**: Database error "users have no column named totp_secret" on TOTP verification.

**Solution**: Enhanced `ensure_db_tables()` to check for and add the `totp_secret` column if missing:
```python
# If the existing users table lacks a totp_secret column, migrate it
cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
if 'totp_secret' not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
```

**Verification**: ✅ Database schema now includes: `['id', 'email', 'password', 'totp_secret']`

### 4. **Incorrect Variable References** ✅
**Problem**: 
- `complete_signup()` referenced `self.totp_input` which didn't exist
- `show_totp_enroll_ui()` tried to access `self.modal_qr_image` before it was created

**Solution**:
- Updated `complete_signup()` to use `self.modal_totp_input` (the actual attribute created in `build_totp_modal()`)
- Reordered `show_totp_enroll_ui()` to build the modal first, then update the QR image

### 5. **SQL Syntax Error** ✅
**Problem**: In the bcrypt legacy fallback, UPDATE statement was malformed: `"UPDATE users SET password = ? WHERE email = "` (missing `?`)

**Solution**: Fixed the SQL statement:
```python
cursor.execute("UPDATE users SET password = ? WHERE email = ?", (new_hash, user))
```

### 6. **UI Layout Issues** ✅
**Problem**: KV file had nested `Screen` widgets inside screen rules, causing touch event blocking and overlay issues.

**Solution**: Removed the nested `<homeScreen>`, `<signUp>`, etc. rule definitions that contained `Screen:` and `<...>:` blocks inside them. The actual screen content is now directly in the rule rules with `FloatLayout` and `MDCard`.

**Result**: 
- Modal TOTP popups now appear on top of background screens
- Touch events properly reach input fields and buttons
- No more invisible overlay blocking interactions

### 7. **Removed Unused Imports** ✅
Cleaned up unused imports to eliminate linter warnings:
- `from kivy.uix.image import Image as KivyImage` (unused alias)
- `from kivy.metrics import dp` (not used in code)
- `from kivymd.uix.button import MDFlatButton` (duplicate import)
- `from kivy.app import App` (unused)

---

## How TOTP Flow Now Works

### Sign-Up Flow
1. User enters email and password
2. Clicks "Create account"
3. **Modal appears** (built fresh) with:
   - QR code for authenticator app
   - 6-digit code input field
   - "Verify & Create Account" and "Cancel" buttons
4. User scans QR, enters 6-digit code, clicks verify
5. Account is created with password hash + TOTP secret stored in DB
6. Modal dismisses, user returned to login screen

### Login Flow
1. User enters email and password
2. Clicks "Sign in"
3. Password is verified (Argon2id)
4. **Modal appears** (built fresh) with:
   - 6-digit code input field
   - "Verify" button
5. User enters 6-digit code from authenticator app
6. Code verified against stored TOTP secret
7. Session token created and stored
8. User redirected to signed-in screen

---

## Testing Checklist

- [x] Imports successful without errors
- [x] Database schema includes `totp_secret` column
- [x] Modals build and open without reparenting errors
- [x] No linter errors on import statements
- [x] Modal instances are fresh on each call (avoiding reparenting)

---

## Files Modified

1. **services/Main.py**
   - Added missing KivyMD imports
   - Refactored modal creation to build on-demand
   - Fixed variable references in `complete_signup()` and `show_totp_enroll_ui()`
   - Fixed SQL syntax error in bcrypt fallback
   - Removed unused imports

2. **ui/main.kv**
   - Removed nested `Screen:` rules that caused layout issues
   - Simplified screen rules to use `FloatLayout` directly
   - Removed duplicate TOTP UI blocks (now handled by Python modals)


