# Programmatic test that calls homeScreen.verify without running the Kivy app UI.
# It patches UI-dependent methods (show_popup, clear_fields) and provides minimal ids.
from types import SimpleNamespace
import services.Main as M

hs = M.homeScreen()
# provide minimal ids used by verify and show_totp_box
hs.ids = {
    'totp_box': SimpleNamespace(opacity=0, disabled=True, height=0),
    'totp_input': SimpleNamespace(focus=False, text='')
}
# patch UI methods to print instead of opening dialogs
hs.show_popup = lambda title, msg: print(f'[POPUP] {title}: {msg}')
hs.clear_fields = lambda: print('[UI] clear_fields called')
# run verify with known smoke test user and password
print('Calling verify...')
ok = hs.verify('smoke@example.com', 'Abcd1234!')
print('verify returned:', ok)
print('pending_user_email:', hs.pending_user_email)

