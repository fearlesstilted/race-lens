import json
from datetime import UTC, datetime

import pytest

from racelens.recorder import feed as feed_module
from racelens.recorder.feed import inspect_feed, isolate_session, session_info_matches
from racelens.recorder.schedule import ScheduledSession


SESSION = ScheduledSession(
    2026, 13, "Belgian Grand Prix", "FP2", datetime(2026, 7, 17, 15, tzinfo=UTC)
)


def _line(category, payload, timestamp=""):
    encoded = json.dumps(payload) if not timestamp else payload
    return repr([category, encoded, timestamp])


def _info(name="Belgian Grand Prix", number=13, kind="Practice 2", year=2026):
    return {
        "Meeting": {"Name": name, "Number": number},
        "Name": kind,
        "StartDate": f"{year}-07-17T17:00:00",
    }


def test_identity_requires_all_schedule_fields():
    assert session_info_matches(_info(), SESSION)
    assert not session_info_matches(_info(name="British Grand Prix"), SESSION)
    assert not session_info_matches(_info(number=12), SESSION)
    assert not session_info_matches(_info(kind="Practice 1"), SESSION)
    assert not session_info_matches(_info(year=2025), SESSION)


def test_stale_finished_keyframe_does_not_finish_target(tmp_path):
    path = tmp_path / "raw.txt"
    path.write_text("\n".join([
        _line("SessionInfo", _info("British Grand Prix", 12, "Race")),
        _line("SessionStatus", {"Status": "Finalised"}),
    ]), encoding="utf-8")

    result = inspect_feed(path, SESSION)
    assert not result.matched
    assert not result.finished


def test_isolate_drops_stale_session_and_keeps_driver_names(tmp_path):
    source = tmp_path / "raw.txt"
    destination = tmp_path / "clean.txt"
    stale = _line("RaceControlMessages", {"Messages": [{"Message": "OLD"}]})
    driver_list = _line("DriverList", {"1": {"Tla": "VER"}})
    target_info = _line("SessionInfo", _info(), "2026-07-17T14:55:00Z")
    finished = _line("SessionStatus", {"Status": "Finished"}, "2026-07-17T16:01:00Z")
    source.write_text("\n".join([stale, driver_list, target_info, finished]), encoding="utf-8")

    result = inspect_feed(source, SESSION)
    assert result.matched and result.finished
    isolate_session(source, destination, SESSION)

    clean = destination.read_text(encoding="utf-8")
    assert "OLD" not in clean
    assert "DriverList" in clean
    assert "Belgian Grand Prix" in clean


def test_repeated_target_session_info_does_not_cut_earlier_capture(tmp_path):
    source = tmp_path / "raw.txt"
    destination = tmp_path / "clean.txt"
    early = _line("TimingData", {"Lines": {"1": {"Position": "1"}}})
    source.write_text("\n".join([
        _line("SessionInfo", _info()), early,
        _line("SessionInfo", {**_info(), "SessionStatus": "Finalised"}),
        _line("SessionStatus", {"Status": "Finalised"}),
    ]), encoding="utf-8")

    isolate_session(source, destination, SESSION)

    assert early in destination.read_text(encoding="utf-8")
    assert inspect_feed(source, SESSION).finished


def test_inspection_only_parses_appended_rows(tmp_path, monkeypatch):
    source = tmp_path / "raw.txt"
    source.write_text(_line("SessionInfo", _info()) + "\n", encoding="utf-8")
    seen = []
    parse = feed_module._row
    monkeypatch.setattr(
        feed_module,
        "_row",
        lambda raw: (seen.append(raw), parse(raw))[1],
    )

    inspection = inspect_feed(source, SESSION)
    seen.clear()
    inspection = inspect_feed(source, SESSION, inspection)
    assert seen == []

    with source.open("a", encoding="utf-8") as handle:
        handle.write(_line("SessionStatus", {"Status": "Finished"}) + "\n")
    inspection = inspect_feed(source, SESSION, inspection)
    assert inspection.finished
    assert len(seen) == 1


def test_next_session_bounds_target_segment(tmp_path):
    source = tmp_path / "raw.txt"
    destination = tmp_path / "clean.txt"
    source.write_text("\n".join([
        _line("SessionInfo", _info()),
        _line("TimingData", {"Lines": {"1": {"Position": "1"}}}),
        _line("SessionInfo", _info(kind="Practice 3")),
        _line("RaceControlMessages", {"Messages": [{"Message": "NEXT"}]}),
    ]), encoding="utf-8")

    isolate_session(source, destination, SESSION)

    assert "NEXT" not in destination.read_text(encoding="utf-8")


def test_isolate_refuses_mismatch_without_touching_destination(tmp_path):
    source = tmp_path / "raw.txt"
    destination = tmp_path / "clean.txt"
    source.write_text(_line("SessionInfo", _info(number=12)), encoding="utf-8")
    destination.write_text("safe", encoding="utf-8")

    with pytest.raises(ValueError, match=SESSION.session_id):
        isolate_session(source, destination, SESSION)
    assert destination.read_text(encoding="utf-8") == "safe"
