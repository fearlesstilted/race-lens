"""Shared utilities for racelens adapters."""
from __future__ import annotations

# Flag-message → session-status mapping.
# More-specific (longer) substrings MUST come before shorter ones that are
# substrings of them.  In particular "CHEQUERED FLAG" must precede "RED FLAG"
# because "CHEQUERED FLAG" contains the substring "RED FLAG"
# (chequeRED FLAG).
STATUS_TABLE: tuple[tuple[str, str], ...] = (
    ("CHEQUERED FLAG", "finished"),
    # VSC endings must come before the generic VSC DEPLOYED and SAFETY CAR DEPLOYED
    ("VIRTUAL SAFETY CAR ENDING", "started"),
    ("VSC ENDING", "started"),
    ("VIRTUAL SAFETY CAR DEPLOYED", "vsc"),
    ("VSC DEPLOYED", "vsc"),
    # "SAFETY CAR IN THIS LAP" means the SC is returning next lap — racing resumes.
    # It must come BEFORE "SAFETY CAR DEPLOYED" (which is a substring-overlap risk).
    ("SAFETY CAR IN THIS LAP", "started"),
    ("SAFETY CAR DEPLOYED", "safety_car"),
    ("RED FLAG", "red_flag"),
    ("GREEN LIGHT", "started"),
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


def fastf1_lap1_start(lap1):
    """Return FastF1's earliest explicit lap-1 start, with legacy fallback."""
    if "LapStartTime" in lap1:
        explicit = lap1["LapStartTime"].dropna()
        if len(explicit):
            return explicit.min()
    derived = (lap1["Time"] - lap1["LapTime"]).dropna()
    if len(derived):
        return derived.min()
    raise ValueError("FastF1 lap 1 has no usable start time; refusing unrebased archive")
