"""Driver of the Day: deterministic algorithmic pick based on race performance."""
from __future__ import annotations
import json
import math
import re
import unicodedata
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from racelens.events.models import Event
from racelens.replay.engine import ReplayEngine

# Scoring weights (document them here):
# positions_gained: 3.0 pts per position gained from start to finish
# had_fastest_lap: flat 15 pts bonus
# recovery_bonus: extra 10 pts if gained >= 5 positions (comeback bonus)
# pit_efficiency: -0.5 pts per extra pit stop above 1 (penalise stop-go strategies slightly)

W_POSITIONS_GAINED = 3.0
W_FASTEST_LAP = 15.0
W_RECOVERY = 10.0  # bonus for 5+ positions gained
W_PIT_EXTRA = -0.5  # per pit beyond 1

AWARD_PROVIDER = "Formula 1 fan vote"
AWARD_SCHEMA_VERSION = 1
MAX_AWARD_BYTES = 4096
MAX_AWARDS_HTML_BYTES = 8 * 1024 * 1024
_REPLAY_ID = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_DRIVER_TLA = re.compile(r"^[A-Z]{3}$")
_SOURCE_URL = re.compile(
    r"^https://www\.formula1\.com/en/results/(\d{4})/awards/driver-of-the-day$"
)
_MEETING_ALIASES = {
    "australian": "australia",
    "chinese": "china",
    "japanese": "japan",
    "spanish": "spain",
    "canadian": "canada",
    "austrian": "austria",
    "british": "great britain",
    "belgian": "belgium",
    "hungarian": "hungary",
    "dutch": "netherlands",
    "italian": "italy",
    "mexico city": "mexico",
    "mexican": "mexico",
    "sao paulo": "brazil",
}


class AwardNotFound(LookupError):
    """The official page does not yet contain the requested meeting."""


class AwardValidationError(ValueError):
    """Official award data is malformed, ambiguous, or mismatched."""


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_script = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts[-1] += data


def official_awards_url(year: int) -> str:
    if not 1950 <= year <= 2100:
        raise ValueError("award year is outside the supported range")
    return f"https://www.formula1.com/en/results/{year}/awards/driver-of-the-day"


def normalize_meeting(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise AwardValidationError("meeting identity is invalid")
    ascii_value = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in ascii_value if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()
    normalized = re.sub(r"\s+grand prix$", "", normalized).strip()
    return _MEETING_ALIASES.get(normalized, normalized)


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _structured_award_rows(html: str) -> list[dict]:
    if not isinstance(html, str) or not html or len(html.encode("utf-8")) > MAX_AWARDS_HTML_BYTES:
        raise AwardValidationError("official awards HTML is invalid")
    parser = _Scripts()
    parser.feed(html)
    decoder = json.JSONDecoder()
    chunks: list[str] = []
    marker = "self.__next_f.push("
    for script in parser.scripts:
        cursor = 0
        while (start := script.find(marker, cursor)) >= 0:
            try:
                value, end = decoder.raw_decode(script, start + len(marker))
            except json.JSONDecodeError as exc:
                raise AwardValidationError("official awards payload is malformed") from exc
            chunks.extend(_strings(value))
            cursor = end
    payload = "".join(chunks)
    accordian_marker = '"accordianData":'
    values: list[object] = []
    cursor = 0
    while (start := payload.find(accordian_marker, cursor)) >= 0:
        try:
            value, end = decoder.raw_decode(payload, start + len(accordian_marker))
        except json.JSONDecodeError as exc:
            raise AwardValidationError("official awards records are malformed") from exc
        values.append(value)
        cursor = end
    if not values:
        raise AwardValidationError("official awards records are absent")

    rows: list[dict] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            if "meetingLocation" in value:
                rows.append(value)
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    for value in values:
        collect(value)
    return rows


def validate_official_award(
    value: object,
    *,
    replay_id: str | None = None,
    replay_drivers: set[str] | None = None,
) -> dict:
    fields = {
        "schema_version", "replay_id", "meeting", "driver", "percentage",
        "provider", "source_url", "fetched_at",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise AwardValidationError("official award fields are invalid")
    replay = value["replay_id"]
    driver = value["driver"]
    percentage = value["percentage"]
    if (
        value["schema_version"] != AWARD_SCHEMA_VERSION
        or not isinstance(replay, str)
        or not _REPLAY_ID.fullmatch(replay)
        or (replay_id is not None and replay != replay_id)
        or not isinstance(value["meeting"], str)
        or normalize_meeting(value["meeting"]) != value["meeting"]
        or not isinstance(driver, str)
        or not _DRIVER_TLA.fullmatch(driver)
        or isinstance(percentage, bool)
        or not isinstance(percentage, (int, float))
        or not math.isfinite(percentage)
        or not 0 <= percentage <= 100
        or value["provider"] != AWARD_PROVIDER
        or not isinstance(value["source_url"], str)
        or not _SOURCE_URL.fullmatch(value["source_url"])
    ):
        raise AwardValidationError("official award metadata is invalid")
    if replay_drivers is not None and driver not in replay_drivers:
        raise AwardValidationError("official award driver is absent from replay")
    try:
        fetched_at = datetime.fromisoformat(str(value["fetched_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AwardValidationError("official award timestamp is invalid") from exc
    if fetched_at.tzinfo is None:
        raise AwardValidationError("official award timestamp is invalid")
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > MAX_AWARD_BYTES:
        raise AwardValidationError("official award record is too large")
    return value


def parse_official_award(
    html: str,
    *,
    year: int,
    meeting: str,
    replay_id: str,
    replay_drivers: set[str],
    fetched_at: datetime | None = None,
) -> dict:
    expected = normalize_meeting(meeting)
    matching = []
    for row in _structured_award_rows(html):
        try:
            same_meeting = normalize_meeting(row.get("meetingLocation")) == expected
        except AwardValidationError:
            same_meeting = False
        if same_meeting:
            matching.append(row)
    if not matching:
        raise AwardNotFound(f"official result is not posted for {meeting}")
    winners = [row for row in matching if row.get("votePosition") == 1]
    if len(winners) != 1:
        raise AwardValidationError("official result is missing or ambiguous")
    winner = winners[0]
    driver = winner.get("driverTLA")
    percentage = winner.get("votePercentage")
    if (
        not isinstance(driver, str)
        or not _DRIVER_TLA.fullmatch(driver)
        or isinstance(percentage, bool)
        or not isinstance(percentage, (int, float))
        or not math.isfinite(percentage)
        or not 0 <= percentage <= 100
    ):
        raise AwardValidationError("official winner is malformed")
    stamp = fetched_at or datetime.now(UTC)
    if stamp.tzinfo is None:
        raise AwardValidationError("fetched_at must include a timezone")
    stamp = stamp.astimezone(UTC)
    record = {
        "schema_version": AWARD_SCHEMA_VERSION,
        "replay_id": replay_id,
        "meeting": expected,
        "driver": driver,
        "percentage": float(percentage),
        "provider": AWARD_PROVIDER,
        "source_url": official_awards_url(year),
        "fetched_at": stamp.isoformat().replace("+00:00", "Z"),
    }
    return validate_official_award(
        record, replay_id=replay_id, replay_drivers=replay_drivers,
    )


def award_key(replay_id: str) -> str:
    if not isinstance(replay_id, str) or not _REPLAY_ID.fullmatch(replay_id):
        raise ValueError("invalid replay ID")
    return f"awards/driver-of-the-day/{replay_id}.json"


def persist_official_award(record: dict, root: Path, store: Any | None = None) -> None:
    from racelens.recorder.postprocess import atomic_write_text

    record = validate_official_award(record)
    path = Path(root) / award_key(record["replay_id"])
    atomic_write_text(path, json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    if store is not None:
        store.put_json(award_key(record["replay_id"]), record)


def load_official_award(
    root: Path,
    store: Any | None,
    replay_id: str,
    replay_drivers: set[str],
) -> dict | None:
    path = Path(root) / award_key(replay_id)
    if path.exists():
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_AWARD_BYTES:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            return validate_official_award(
                value, replay_id=replay_id, replay_drivers=replay_drivers,
            )
        except (OSError, json.JSONDecodeError, AwardValidationError):
            return None
    if store is None:
        return None
    try:
        value = store.get_json(award_key(replay_id), limit=MAX_AWARD_BYTES)
        if value is None:
            return None
        return validate_official_award(
            value, replay_id=replay_id, replay_drivers=replay_drivers,
        )
    except (RuntimeError, ValueError):
        return None


def replay_drivers(path: Path) -> set[str]:
    from racelens.events.models import load_jsonl

    events = load_jsonl(Path(path).read_text(encoding="utf-8"))
    return {event.driver_id for event in events if event.driver_id is not None}


def fetch_official_awards_html(
    year: int, *, opener=urllib.request.urlopen,
) -> str:
    request = urllib.request.Request(
        official_awards_url(year),
        headers={"Accept": "text/html", "User-Agent": "race-lens/0.1"},
    )
    with opener(request, timeout=15) as response:
        raw = response.read(MAX_AWARDS_HTML_BYTES + 1)
    if len(raw) > MAX_AWARDS_HTML_BYTES:
        raise AwardValidationError("official awards HTML is too large")
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AwardValidationError("official awards HTML encoding is invalid") from exc
    return html


def fetch_official_award(
    year: int,
    meeting: str,
    replay_id: str,
    replay_drivers_: set[str],
    *,
    opener=urllib.request.urlopen,
) -> dict:
    return parse_official_award(
        fetch_official_awards_html(year, opener=opener),
        year=year,
        meeting=meeting,
        replay_id=replay_id,
        replay_drivers=replay_drivers_,
    )


def sync_official_award(
    year: int,
    meeting: str,
    replay_id: str,
    root: Path,
    store: Any | None = None,
) -> dict:
    drivers = replay_drivers(Path(root) / f"{replay_id}.jsonl")
    current = load_official_award(root, None, replay_id, drivers)
    record = current or fetch_official_award(year, meeting, replay_id, drivers)
    persist_official_award(record, root, store)
    return record


def sync_completed_official_awards(
    year: int,
    sessions,
    root: Path,
    store: Any | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    from racelens.catalog import local_replay_id

    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    pending: list[tuple[object, str, set[str]]] = []
    synced: list[str] = []
    for session in sessions:
        if session.year != year or session.kind != "R" or session.capture_until > current_time:
            continue
        replay_id = local_replay_id(session, Path(root))
        if replay_id is None:
            continue
        fixture = Path(root) / f"{replay_id}.jsonl"
        drivers = replay_drivers(fixture)
        existing = load_official_award(root, store, replay_id, drivers)
        if existing is not None:
            persist_official_award(existing, root, store)
            synced.append(replay_id)
        else:
            pending.append((session, replay_id, drivers))
    if not pending:
        return {"synced": synced, "pending": []}

    html = fetch_official_awards_html(year)
    still_pending = []
    for session, replay_id, drivers in pending:
        try:
            record = parse_official_award(
                html,
                year=year,
                meeting=session.event_name,
                replay_id=replay_id,
                replay_drivers=drivers,
            )
        except AwardNotFound:
            still_pending.append(replay_id)
            continue
        persist_official_award(record, root, store)
        synced.append(replay_id)
    return {"synced": synced, "pending": still_pending}


def driver_of_day(
    events: list[Event],
    state_engine: ReplayEngine,
    at_ms: int | None = None,
) -> dict[str, Any]:
    """Compute Driver of the Day candidates.

    Spoiler-free: when `at_ms` is given the pick is computed from the race SO FAR
    (positions gained, fastest lap, pits up to that time) — a provisional pick
    that updates as the race unfolds, exactly like real DOTD voting opening in the
    final laps. Without `at_ms` it uses the full race (the final result).

    Returns:
        {
          candidates: [
            {driver, score, positions_gained, had_fastest_lap, note_en, note_ru},
            ... top 5 desc by score
          ],
          computed_pick: driver_id  # candidate[0].driver
        }
    """
    # Cut-off time — only events at/before it count (spoiler-free).
    final_ms = at_ms if at_ms is not None else max(e.session_time_ms for e in events)

    # Get starting grid: earliest PositionChanged for each driver
    start_positions: dict[str, int] = {}
    for e in sorted(events, key=lambda x: (x.session_time_ms, x.event_id)):
        if e.session_time_ms > final_ms:
            break
        if e.type == "PositionChanged" and e.driver_id not in start_positions:
            pos = e.payload.get("position")
            if pos is not None:
                start_positions[e.driver_id] = pos

    # State as of the cut-off
    final_state = state_engine.state_at(final_ms)
    drivers_state = final_state["drivers"]

    # Find absolute fastest lap in the race
    best_lap_ms: int | None = None
    for ds in drivers_state.values():
        bl = ds.get("best_lap_ms")
        if bl is not None and (best_lap_ms is None or bl < best_lap_ms):
            best_lap_ms = bl
    fastest_lap_holder: str | None = None
    if best_lap_ms is not None:
        for drv, ds in drivers_state.items():
            if ds.get("best_lap_ms") == best_lap_ms:
                fastest_lap_holder = drv
                break

    candidates = []
    for drv, ds in drivers_state.items():
        if ds.get("retired"):
            continue
        if ds.get("position") is None:
            continue

        start_pos = start_positions.get(drv)
        final_pos = ds.get("position")
        if start_pos is None or final_pos is None:
            continue

        positions_gained = start_pos - final_pos  # positive = moved forward
        had_fastest_lap = (drv == fastest_lap_holder)
        extra_pits = max(0, ds.get("pit_count", 1) - 1)

        score = (
            positions_gained * W_POSITIONS_GAINED
            + (W_FASTEST_LAP if had_fastest_lap else 0.0)
            + (W_RECOVERY if positions_gained >= 5 else 0.0)
            + extra_pits * W_PIT_EXTRA
        )

        # Human-readable note
        if positions_gained > 0:
            note_en = f"Gained {positions_gained} position{'s' if positions_gained != 1 else ''} (P{start_pos}→P{final_pos})"
            note_ru = f"Отыграл {positions_gained} позиц. (P{start_pos}→P{final_pos})"
        elif positions_gained == 0:
            note_en = f"Held P{final_pos}"
            note_ru = f"Удержал P{final_pos}"
        else:
            note_en = f"Lost {-positions_gained} positions (P{start_pos}→P{final_pos})"
            note_ru = f"Потерял {-positions_gained} позиц. (P{start_pos}→P{final_pos})"

        if had_fastest_lap:
            note_en += " + fastest lap"
            note_ru += " + быстрейший круг"

        candidates.append({
            "driver": drv,
            "score": round(score, 2),
            "positions_gained": positions_gained,
            "had_fastest_lap": had_fastest_lap,
            "note_en": note_en,
            "note_ru": note_ru,
        })

    # Sort by score desc, then driver code for determinism
    candidates.sort(key=lambda c: (-c["score"], c["driver"]))

    top5 = candidates[:5]
    computed_pick = top5[0]["driver"] if top5 else None

    return {
        "candidates": top5,
        "computed_pick": computed_pick,
    }
