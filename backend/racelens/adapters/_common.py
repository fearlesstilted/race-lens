"""Shared utilities for racelens adapters."""
from __future__ import annotations

# Flag-message → session-status mapping.
# More-specific (longer) substrings MUST come before shorter ones that are
# substrings of them.  In particular "CHEQUERED FLAG" must precede "RED FLAG"
# because "CHEQUERED FLAG" contains the substring "RED FLAG"
# (chequeRED FLAG).
STATUS_TABLE: tuple[tuple[str, str], ...] = (
    ("CHEQUERED FLAG", "finished"),
    ("VIRTUAL SAFETY CAR DEPLOYED", "vsc"),
    ("SAFETY CAR DEPLOYED", "safety_car"),
    ("RED FLAG", "red_flag"),
    ("GREEN LIGHT", "started"),
    ("TRACK CLEAR", "started"),
)


def message_to_status(text: str, table: tuple[tuple[str, str], ...] = STATUS_TABLE) -> str | None:
    """Return the first matching status for *text* using first-match semantics.

    Case-insensitive match against each needle in *table*.  Returns ``None``
    when no needle matches.
    """
    upper = text.upper()
    for needle, status in table:
        if needle in upper:
            return status
    return None
