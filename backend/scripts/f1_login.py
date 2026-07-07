"""One-time F1 account login → token cache for the authenticated SignalR feed.

Run interactively (opens a browser), then live/start?auth=1 works headless:

    python3 scripts/f1_login.py
"""
from fastf1.internals import f1auth

f1auth.get_auth_token()  # opens browser on first run, cached afterwards
f1auth.print_auth_status()
