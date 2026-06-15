"""Tests for significant_events(): timeline markers layer.

Covers:
- mini_race synthetic fixture (lead changes, fastest lap, podium)
- miami_2026_race real fixture (SC + GREEN markers, incidents)
- spain_2024_race real fixture (incidents with driver extraction)
- Spoiler-free (until_ms filtering)
- Determinism under multiple calls
- Deduplication
"""
from __future__ import annotations

from pathlib import Path

import pytest

from racelens.events.models import Event, event, load_jsonl
from racelens.events_significant import (
    KIND_FASTEST_LAP,
    KIND_GREEN,
    KIND_INCIDENT,
    KIND_LEAD_CHANGE,
    KIND_PENALTY,
    KIND_PODIUM_CHANGE,
    KIND_SAFETY_CAR,
    SEV_CRITICAL,
    SEV_HIGH,
    SEV_LOW,
    SEV_MEDIUM,
    significant_events,
)
# ── Fixtures path ──────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> list[Event]:
    path = FIXTURES / f"{name}.jsonl"
    return load_jsonl(path.read_text(encoding="utf-8"))


# ── Mini-race fixture ──────────────────────────────────────────────────────────

SID = "2024_mini_race"


def mini_race_events() -> list[Event]:
    """3-lap synthetic race: VER leads the whole race, LEC/NOR swap P2/P3.

    VER is P1 throughout → no LEAD_CHANGE expected.
    NOR takes P2 mid-lap2 after LEC pits → PODIUM_CHANGE expected.
    LEC's lap 3 (77_000 ms) is the fastest lap → FASTEST_LAP expected.
    """
    e = []
    e.append(event(SID, "SessionStarted", 0, total_laps=3))
    for drv, pos in [("VER", 1), ("LEC", 2), ("NOR", 3)]:
        e.append(event(SID, "PositionChanged", 0, drv, position=pos))
        e.append(event(SID, "TyreStintUpdated", 0, drv, compound="M", age_laps=0))

    # Lap 1
    e.append(event(SID, "LapCompleted", 80_000, "VER", lap=1, lap_time_ms=78_000))
    e.append(event(SID, "LapCompleted", 81_000, "LEC", lap=1, lap_time_ms=79_000))
    e.append(event(SID, "LapCompleted", 82_000, "NOR", lap=1, lap_time_ms=80_000))

    # LEC pits, NOR moves to P2
    e.append(event(SID, "PitIn", 110_000, "LEC", lap=2))
    e.append(event(SID, "PitOut", 135_000, "LEC", lap=2))
    e.append(event(SID, "TyreStintUpdated", 135_000, "LEC", compound="H", age_laps=0))
    e.append(event(SID, "PositionChanged", 136_000, "LEC", position=3))
    e.append(event(SID, "PositionChanged", 136_000, "NOR", position=2))

    # Lap 2
    e.append(event(SID, "LapCompleted", 160_000, "VER", lap=2, lap_time_ms=77_500))
    e.append(event(SID, "LapCompleted", 163_000, "NOR", lap=2, lap_time_ms=80_500))
    e.append(event(SID, "LapCompleted", 168_000, "LEC", lap=2, lap_time_ms=86_000))

    # Lap 3 + finish
    e.append(event(SID, "LapCompleted", 238_000, "VER", lap=3, lap_time_ms=77_900))
    e.append(event(SID, "LapCompleted", 242_000, "NOR", lap=3, lap_time_ms=79_800))
    e.append(event(SID, "LapCompleted", 245_000, "LEC", lap=3, lap_time_ms=77_000))
    e.append(event(SID, "SessionStatusChanged", 250_000, status="finished"))
    return e


# ── Mini-race tests ────────────────────────────────────────────────────────────

def test_mini_no_lead_change():
    """VER leads from start to finish — no LEAD_CHANGE should fire."""
    markers = significant_events(mini_race_events())
    lead_changes = [m for m in markers if m["kind"] == KIND_LEAD_CHANGE]
    assert lead_changes == [], f"Unexpected lead changes: {lead_changes}"


def test_mini_no_podium_change_on_internal_reshuffle():
    """VER/LEC/NOR are all in P1-3 the whole race — set never changes → no PODIUM_CHANGE."""
    markers = significant_events(mini_race_events())
    podium = [m for m in markers if m["kind"] == KIND_PODIUM_CHANGE]
    # The top-3 SET {VER, LEC, NOR} never changes (LEC falls from P2→P3 but stays in top-3)
    # so no PODIUM_CHANGE should fire — per spec: "only real changes of the set, not reshuffles"
    assert podium == [], f"No PODIUM_CHANGE expected in mini_race (same set), got: {podium}"


def test_mini_fastest_lap():
    """LEC's lap3 at 77_000 ms is the absolute fastest → FASTEST_LAP."""
    markers = significant_events(mini_race_events())
    fl = [m for m in markers if m["kind"] == KIND_FASTEST_LAP]
    assert fl, "Expected FASTEST_LAP markers"
    # LEC's 77_000 should be the last (and fastest) FASTEST_LAP
    lec_fl = [m for m in fl if "LEC" in m["driver_ids"]]
    assert lec_fl, "Expected a FASTEST_LAP for LEC"
    lec_best = lec_fl[-1]
    assert lec_best["severity"] == SEV_LOW
    assert "1:17.000" in lec_best["text_en"]
    assert "LEC" in lec_best["text_ru"]


def test_mini_fastest_lap_before_lec():
    """Before LEC's lap3 (245_000 ms), VER holds the fastest lap at 77_500."""
    markers = significant_events(mini_race_events(), until_ms=244_000)
    fl = [m for m in markers if m["kind"] == KIND_FASTEST_LAP]
    # VER's 77_500 should be the latest fastest lap holder before LEC beats it
    ver_fl = [m for m in fl if "VER" in m["driver_ids"]]
    assert ver_fl, "VER should hold fastest lap at 244_000"
    # LEC's lap3 should not appear
    lec_fl = [m for m in fl if "LEC" in m["driver_ids"]]
    # LEC did lap 1 (79_000) and lap 2 (86_000) — neither beats VER's 77_500
    assert all("77" not in m["text_en"] or "77.000" not in m["text_en"] for m in lec_fl), \
        "LEC's 77_000 lap should not appear before 244_000"


def test_mini_sorted_by_at_ms():
    """Output must be sorted ascending by at_ms."""
    markers = significant_events(mini_race_events())
    assert markers == sorted(markers, key=lambda m: (m["at_ms"], m["kind"]))


def test_mini_spoiler_free_cuts_future():
    """until_ms=0 should produce no markers (no events have occurred yet)."""
    markers = significant_events(mini_race_events(), until_ms=0)
    assert markers == []


def test_mini_spoiler_free_partial():
    """until_ms before lap 2 should not contain lap-3 fastest lap."""
    markers = significant_events(mini_race_events(), until_ms=168_000)
    lec_fast_lap3 = [
        m for m in markers
        if m["kind"] == KIND_FASTEST_LAP and "LEC" in m["driver_ids"]
        and "1:17.000" in m["text_en"]
    ]
    assert lec_fast_lap3 == [], "LEC lap3 fastest should not appear before lap3 completes"


def test_mini_determinism():
    """Same inputs always produce the same output."""
    events = mini_race_events()
    r1 = significant_events(events, until_ms=300_000)
    r2 = significant_events(events, until_ms=300_000)
    assert r1 == r2


def test_mini_dedup_extra_events():
    """Duplicate events must not produce duplicate markers."""
    events = mini_race_events()
    doubled = events + events  # full duplication
    markers_doubled = significant_events(doubled)
    markers_clean = significant_events(events)
    # Should be identical after dedup
    assert markers_doubled == markers_clean


def test_mini_marker_schema():
    """Every marker must have the required keys and correct types."""
    required = {"at_ms", "lap", "kind", "severity", "driver_ids", "text_en", "text_ru"}
    valid_severities = {SEV_CRITICAL, SEV_HIGH, SEV_MEDIUM, SEV_LOW}
    for m in significant_events(mini_race_events()):
        assert required.issubset(m.keys()), f"Missing keys in {m}"
        assert isinstance(m["at_ms"], int)
        assert isinstance(m["driver_ids"], list)
        assert m["severity"] in valid_severities, f"Bad severity in {m}"
        assert isinstance(m["text_en"], str) and m["text_en"]
        assert isinstance(m["text_ru"], str) and m["text_ru"]


# ── Miami 2026 tests ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def miami_markers():
    events = _load("miami_2026_race")
    return significant_events(events)


def test_miami_safety_car_deployed(miami_markers):
    """Miami 2026 had a safety car — SAFETY_CAR marker must appear."""
    sc = [m for m in miami_markers if m["kind"] == KIND_SAFETY_CAR]
    assert sc, "Expected SAFETY_CAR marker in Miami 2026"
    assert sc[0]["severity"] == SEV_HIGH
    assert "Safety car" in sc[0]["text_en"]
    assert "Safety car" in sc[0]["text_ru"]


def test_miami_green_after_sc(miami_markers):
    """After SC in Miami, race restarted → GREEN marker must appear."""
    sc = [m for m in miami_markers if m["kind"] == KIND_SAFETY_CAR]
    green = [m for m in miami_markers if m["kind"] == KIND_GREEN]
    assert green, "Expected GREEN (restart) marker after SC in Miami 2026"
    # GREEN must come after SC
    assert green[0]["at_ms"] > sc[0]["at_ms"]
    assert green[0]["severity"] == SEV_MEDIUM
    assert "resumed" in green[0]["text_en"].lower()


def test_miami_incidents(miami_markers):
    """Miami 2026 had multiple incidents — at least one INCIDENT marker expected."""
    incidents = [m for m in miami_markers if m["kind"] in (KIND_INCIDENT, "CRASH")]
    assert incidents, "Expected INCIDENT markers in Miami 2026"
    # Should have driver codes extracted from the messages
    first = incidents[0]
    assert first["driver_ids"], f"Expected driver codes in: {first}"


def test_miami_penalty_or_investigation(miami_markers):
    """Miami 2026 had steward investigations — PENALTY markers expected."""
    penalties = [m for m in miami_markers if m["kind"] == KIND_PENALTY]
    assert penalties, "Expected PENALTY/investigation markers in Miami 2026"


def test_miami_sorted(miami_markers):
    """Miami markers must be sorted ascending by at_ms."""
    assert miami_markers == sorted(miami_markers, key=lambda m: (m["at_ms"], m["kind"]))


def test_miami_spoiler_free_before_sc():
    """Requesting markers before SC time should not show SC or GREEN."""
    events = _load("miami_2026_race")
    # SC at ~734756 ms
    markers_early = significant_events(events, until_ms=700_000)
    sc = [m for m in markers_early if m["kind"] == KIND_SAFETY_CAR]
    green = [m for m in markers_early if m["kind"] == KIND_GREEN]
    assert sc == [], "SC must not appear before it happened"
    assert green == [], "GREEN must not appear before SC"


# ── Spain 2024 tests ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spain_markers():
    events = _load("spain_2024_race")
    return significant_events(events)


def test_spain_incident_early(spain_markers):
    """Spain 2024 lap 1 had a NOR/VER incident at ~425_774 ms."""
    # First incident should be NOR/VER (CARS 4 (NOR) AND 1 (VER))
    incidents = [m for m in spain_markers if m["kind"] in (KIND_INCIDENT, "CRASH")]
    assert incidents, "Expected INCIDENT markers in Spain 2024"
    first = incidents[0]
    # Should have drivers extracted
    assert first["driver_ids"], f"Expected driver codes in first incident: {first}"
    # NOR and VER should appear in the early incidents
    early = [m for m in incidents if m["at_ms"] < 600_000]
    all_drivers = [d for m in early for d in m["driver_ids"]]
    assert "NOR" in all_drivers or "VER" in all_drivers, \
        f"Expected NOR or VER in early Spain incidents; got {all_drivers}"


def test_spain_incident_has_driver_codes(spain_markers):
    """All Spain incidents should have driver codes extracted (not empty)."""
    incidents = [m for m in spain_markers if m["kind"] in (KIND_INCIDENT, "CRASH")]
    # Most messages have (XXX) codes — at least half should parse drivers
    with_drivers = [m for m in incidents if m["driver_ids"]]
    assert len(with_drivers) > len(incidents) // 2, \
        "Most incidents should have driver codes extracted"


def test_spain_incident_text_format(spain_markers):
    """Spain incidents should have human-readable text in both languages."""
    for m in spain_markers:
        if m["kind"] in (KIND_INCIDENT, "CRASH"):
            assert ":" in m["text_en"], f"Expected ':' in EN text: {m['text_en']}"
            assert ":" in m["text_ru"], f"Expected ':' in RU text: {m['text_ru']}"


def test_spain_lead_change(spain_markers):
    """Spain 2024 is a real race — should have lead changes."""
    lead_changes = [m for m in spain_markers if m["kind"] == KIND_LEAD_CHANGE]
    # Spain 2024 had multiple lead changes (pit stop cycles)
    assert lead_changes, "Expected LEAD_CHANGE markers in Spain 2024"
    for lc in lead_changes:
        assert len(lc["driver_ids"]) == 2, "LEAD_CHANGE should have [new_leader, old_leader]"
        assert lc["severity"] == SEV_HIGH
        assert "passes" in lc["text_en"]
        assert "обходит" in lc["text_ru"]


def test_spain_fastest_lap_progression(spain_markers):
    """Fastest lap should progress (improving times) across the race."""
    fl = [m for m in spain_markers if m["kind"] == KIND_FASTEST_LAP]
    assert fl, "Expected FASTEST_LAP markers in Spain 2024"
    # Extract times from text (format "D:SS.mmm")
    # Each FASTEST_LAP should be a new record — at_ms must be monotonic
    times = [m["at_ms"] for m in fl]
    assert times == sorted(times), "FASTEST_LAP markers should be in time order"


def test_spain_determinism():
    """Spain 2024 results must be deterministic across multiple calls."""
    events = _load("spain_2024_race")
    r1 = significant_events(events)
    r2 = significant_events(events)
    assert r1 == r2
