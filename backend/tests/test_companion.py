import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.companion import CompanionRelay, CompanionState  # noqa: E402


REPLAY_STATE = {
    "race_id": "bahrain_2021_race",
    "mode": "replay",
    "at_ms": 123_000,
    "selected_driver_ids": ["VER", "44"],
}
LIVE_STATE = {
    "race_id": "2026-14-r",
    "mode": "live",
    "at_ms": None,
    "selected_driver_ids": ["NOR"],
}


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.started = datetime(2026, 9, 1, 12, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.elapsed

    def utcnow(self) -> datetime:
        return self.started + timedelta(seconds=self.elapsed)


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def relay(clock: Clock) -> CompanionRelay:
    return CompanionRelay(clock=clock.monotonic, utcnow=clock.utcnow)


@pytest.fixture()
def client(monkeypatch, relay: CompanionRelay) -> TestClient:
    import racelens.api as api

    monkeypatch.setattr(api, "_companion_relay", relay)
    return TestClient(api.app)


def create_link(client: TestClient, state: dict | None = None) -> dict:
    response = client.post("/api/companion-links", json={"state": state or REPLAY_STATE})
    assert response.status_code == 200, response.text
    return response.json()


def auth(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def test_authentication_keeps_secret_out_of_storage_and_non_create_responses(
    client: TestClient,
    relay: CompanionRelay,
) -> None:
    created = create_link(client)
    link_id, secret = created["link_id"], created["secret"]
    assert set(created) == {"link_id", "secret", "revision", "expires_at", "state"}
    assert len(secret) >= 40
    assert secret not in repr(relay)
    stored = relay._links[link_id]
    assert not hasattr(stored, "secret")
    assert stored.secret_digest == hashlib.sha256(secret.encode()).digest()

    missing = client.get(f"/api/companion-links/{link_id}")
    invalid = client.get(f"/api/companion-links/{link_id}", headers=auth("wrong"))
    query_only = client.get(f"/api/companion-links/{link_id}?secret={secret}")
    assert missing.status_code == invalid.status_code == query_only.status_code == 401
    assert secret not in missing.text + invalid.text + query_only.text
    assert invalid.json() == {"detail": "Invalid companion authorization"}

    fetched = client.get(f"/api/companion-links/{link_id}", headers=auth(secret))
    assert fetched.status_code == 200
    assert set(fetched.json()) == {"link_id", "revision", "expires_at", "state"}


@pytest.mark.parametrize(
    "state",
    [
        {**REPLAY_STATE, "at_ms": None},
        {**LIVE_STATE, "at_ms": 0},
        {**REPLAY_STATE, "race_id": "2026/14/r"},
        {**REPLAY_STATE, "selected_driver_ids": ["VER", "VER"]},
        {**REPLAY_STATE, "selected_driver_ids": ["VER", "NOR", "LEC"]},
        {**REPLAY_STATE, "selected_driver_ids": ["verstappen"]},
        {**REPLAY_STATE, "unexpected": True},
    ],
)
def test_state_rejects_invalid_or_extra_fields(client: TestClient, state: dict) -> None:
    assert client.post("/api/companion-links", json={"state": state}).status_code == 422


def test_request_envelopes_forbid_extra_fields(client: TestClient) -> None:
    assert client.post(
        "/api/companion-links",
        json={"state": REPLAY_STATE, "extra": "no"},
    ).status_code == 422
    created = create_link(client)
    response = client.patch(
        f"/api/companion-links/{created['link_id']}",
        headers=auth(created["secret"]),
        json={"expected_revision": 0, "state": REPLAY_STATE, "extra": "no"},
    )
    assert response.status_code == 422


def test_patch_conflicts_and_revisions_are_monotonic(client: TestClient) -> None:
    created = create_link(client)
    path = f"/api/companion-links/{created['link_id']}"
    headers = auth(created["secret"])

    first = client.patch(
        path,
        headers=headers,
        json={"expected_revision": 0, "state": LIVE_STATE},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert "secret" not in first.json()

    stale = client.patch(
        path,
        headers=headers,
        json={"expected_revision": 0, "state": REPLAY_STATE},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "Companion link revision conflict"}

    second = client.patch(
        path,
        headers=headers,
        json={"expected_revision": 1, "state": REPLAY_STATE},
    )
    assert second.status_code == 200
    assert second.json()["revision"] == 2


def test_expired_link_is_distinct_from_unknown(
    client: TestClient,
    clock: Clock,
) -> None:
    created = create_link(client)
    clock.elapsed = 7200

    expired = client.get(
        f"/api/companion-links/{created['link_id']}",
        headers=auth(created["secret"]),
    )
    unknown = client.get(
        "/api/companion-links/Abcdefghijklmnop",
        headers=auth(created["secret"]),
    )
    assert expired.status_code == 410
    assert unknown.status_code == 404


def test_long_poll_wakes_on_update_and_returns_unchanged_on_timeout() -> None:
    async def scenario() -> None:
        relay = CompanionRelay()
        first = await relay.create(CompanionState.model_validate(REPLAY_STATE))

        waiter = asyncio.create_task(
            relay.read(first.link_id, first.secret, after_revision=0, wait_seconds=0.5)
        )
        await asyncio.sleep(0.01)
        updated = await relay.replace(
            first.link_id,
            first.secret,
            expected_revision=0,
            state=CompanionState.model_validate(LIVE_STATE),
        )
        assert updated.revision == 1
        assert (await asyncio.wait_for(waiter, timeout=0.5)).revision == 1

        unchanged = await relay.read(
            first.link_id,
            first.secret,
            after_revision=1,
            wait_seconds=0.01,
        )
        assert unchanged.revision == 1

    asyncio.run(scenario())


def test_capacity_is_bounded_and_expired_rooms_are_cleaned_lazily(
    monkeypatch,
    clock: Clock,
) -> None:
    import racelens.api as api

    relay = CompanionRelay(max_links=1, clock=clock.monotonic, utcnow=clock.utcnow)
    monkeypatch.setattr(api, "_companion_relay", relay)
    client = TestClient(api.app)
    first = create_link(client)

    full = client.post("/api/companion-links", json={"state": REPLAY_STATE})
    assert full.status_code == 503
    assert full.json() == {"detail": "Companion link capacity reached"}

    clock.elapsed = 7200
    second = create_link(client, LIVE_STATE)
    assert second["link_id"] != first["link_id"]
    expired = client.get(
        f"/api/companion-links/{first['link_id']}",
        headers=auth(first["secret"]),
    )
    assert expired.status_code == 410


def test_cors_allows_authorization_and_patch(client: TestClient) -> None:
    response = client.options(
        "/api/companion-links/Abcdefghijklmnop",
        headers={
            "Origin": "https://race-lens.onrender.com",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://race-lens.onrender.com"
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_companion_path_serves_spa_and_missing_dist_is_honest(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    import racelens.api as api

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>Race Lens</main>", encoding="utf-8")
    monkeypatch.setattr(api, "_DIST", dist)
    response = client.get("/companion/Abcdefghijklmnop")
    assert response.status_code == 200
    assert response.text == "<main>Race Lens</main>"

    monkeypatch.setattr(api, "_DIST", tmp_path / "missing")
    assert client.get("/companion/Abcdefghijklmnop").status_code == 404
    assert client.get("/companion/not-valid").status_code == 404
