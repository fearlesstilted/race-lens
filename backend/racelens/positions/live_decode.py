"""Position.z live decoder: compressed SignalR car coordinates → viewbox x/y.

The authenticated F1 feed carries a 'Position.z' topic whose payload is
base64(raw-deflate(json)):

    {"Position": [{"Timestamp": "...", "Entries":
        {"1": {"X": -3018, "Y": 5615, "Z": 165, "Status": "OnTrack"}, ...}}]}

X/Y are in the same decimetre frame as archive telemetry, so normalization
reuses the track.json contract (extent_dm + padding + viewbox) — the exact
formula of positions/track.py:build_track_outline, Y inverted.

Wiring into the live frame happens on a live session (needs the racing-number
→ driver-code map from DriverList); this module is the pure decode half.
"""
from __future__ import annotations

import base64
import json
import zlib
from typing import Any


def decode_position_payload(payload: str) -> list[dict[str, Any]]:
    """base64 + raw-deflate 'Position.z' payload → list of position samples.

    Returns [] on undecodable input (feed hiccups must not kill the poll loop).
    Each sample: {"Timestamp": str, "Entries": {racing_number: {X, Y, Z, Status}}}.
    """
    try:
        raw = zlib.decompress(base64.b64decode(payload), -zlib.MAX_WBITS)
        data = json.loads(raw)
    except (ValueError, zlib.error):
        return []
    samples = data.get("Position")
    return samples if isinstance(samples, list) else []


def encode_position_payload(data: dict[str, Any]) -> str:
    """Inverse of decode (tests + fixture tooling)."""
    comp = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = comp.compress(json.dumps(data).encode()) + comp.flush()
    return base64.b64encode(raw).decode()


def normalize_xy(x: float, y: float, track: dict[str, Any]) -> tuple[float, float]:
    """Raw decimetre X/Y → track.json viewbox coordinates (Y inverted).

    Mirrors build_track_outline's normalization so live cars land exactly on
    the drawn outline. `track` is the loaded .track.json dict.
    """
    vw, vh = track.get("viewbox", [600, 400])
    pad = track.get("padding", 20)
    x_min, y_min, x_max, y_max = track["extent_dm"]
    x_range = (x_max - x_min) or 1.0
    y_range = (y_max - y_min) or 1.0
    avail_w = vw - 2 * pad
    avail_h = vh - 2 * pad
    scale = min(avail_w / x_range, avail_h / y_range)
    offset_x = pad + (avail_w - x_range * scale) / 2
    offset_y = pad + (avail_h - y_range * scale) / 2
    nx = round(offset_x + (x - x_min) * scale, 1)
    ny = round(vh - (offset_y + (y - y_min) * scale), 1)
    return nx, ny
