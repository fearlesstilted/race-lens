"""Track-specific parameters for forecast models.

Values are typical empirical estimates from official F1 data and public timing analysis:
- pit_loss_s: total time lost in pit lane (entry + stationary + exit) vs. racing through
- overtake_difficulty: 0.0 = easy overtakes (high-speed straights), 1.0 = nearly impossible (Monaco walls)
"""

TRACK_PARAMS: dict[str, dict] = {
    "monaco": {"pit_loss_s": 21.0, "overtake_difficulty": 0.95},
    "miami": {"pit_loss_s": 19.0, "overtake_difficulty": 0.45},
    "spain": {"pit_loss_s": 21.0, "overtake_difficulty": 0.55},
    "barcelona": {"pit_loss_s": 21.0, "overtake_difficulty": 0.55},
    "austria": {"pit_loss_s": 19.5, "overtake_difficulty": 0.30},
    "silverstone": {"pit_loss_s": 20.0, "overtake_difficulty": 0.40},
    "monza": {"pit_loss_s": 20.5, "overtake_difficulty": 0.35},
    "suzuka": {"pit_loss_s": 20.0, "overtake_difficulty": 0.50},
    "bahrain": {"pit_loss_s": 19.0, "overtake_difficulty": 0.40},
    "jeddah": {"pit_loss_s": 19.5, "overtake_difficulty": 0.60},
    "singapore": {"pit_loss_s": 20.5, "overtake_difficulty": 0.80},
    "canada": {"pit_loss_s": 19.0, "overtake_difficulty": 0.35},
    "interlagos": {"pit_loss_s": 19.5, "overtake_difficulty": 0.40},
    "mexico": {"pit_loss_s": 20.0, "overtake_difficulty": 0.45},
    "abu_dhabi": {"pit_loss_s": 19.5, "overtake_difficulty": 0.45},
}

_DEFAULT_PARAMS: dict = {"pit_loss_s": 21.0, "overtake_difficulty": 0.60}


def track_params(session_id: str) -> dict:
    """Return track parameters for the given session_id.

    Matches by prefix — e.g. 'spain_2024_race' → 'spain' entry.
    Falls back to defaults if no match found.
    """
    sid = session_id.lower()
    for key, params in TRACK_PARAMS.items():
        if sid.startswith(key):
            return params
    return _DEFAULT_PARAMS.copy()
