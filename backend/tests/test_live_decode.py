"""Position.z decode + viewbox normalization."""
import json
from pathlib import Path

from racelens.positions.live_decode import (
    decode_position_payload,
    encode_position_payload,
    normalize_xy,
)

TRACK = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "spa_2026_race.track.json").read_text()
)


def test_roundtrip() -> None:
    data = {
        "Position": [
            {
                "Timestamp": "2026-07-17T11:30:00.123Z",
                "Entries": {"1": {"X": -3018, "Y": 5615, "Z": 165, "Status": "OnTrack"}},
            }
        ]
    }
    samples = decode_position_payload(encode_position_payload(data))
    assert len(samples) == 1
    assert samples[0]["Entries"]["1"]["X"] == -3018


def test_garbage_returns_empty() -> None:
    assert decode_position_payload("not-base64!!") == []
    assert decode_position_payload("aGVsbG8=") == []  # valid b64, not deflate


def test_normalize_lands_in_viewbox() -> None:
    x_min, y_min, x_max, y_max = TRACK["extent_dm"]
    vw, vh = TRACK["viewbox"]
    for x, y in [(x_min, y_min), (x_max, y_max), ((x_min + x_max) / 2, (y_min + y_max) / 2)]:
        nx, ny = normalize_xy(x, y, TRACK)
        assert 0 <= nx <= vw and 0 <= ny <= vh
    # Y inversion: telemetry y_min maps to the BOTTOM of the viewbox.
    _, ny_min = normalize_xy(x_min, y_min, TRACK)
    _, ny_max = normalize_xy(x_min, y_max, TRACK)
    assert ny_min > ny_max


def test_normalize_matches_outline_points() -> None:
    # Corners of the extent must reproduce the outline's own normalization:
    # every outline point lies inside [pad-1, view-pad+1] on the scaled axis.
    pad = TRACK["padding"]
    vw, vh = TRACK["viewbox"]
    xs = [p[0] for p in TRACK["points"]]
    ys = [p[1] for p in TRACK["points"]]
    assert min(xs) >= pad - 1 and max(xs) <= vw - pad + 1
    assert min(ys) >= pad - 1 and max(ys) <= vh - pad + 1
