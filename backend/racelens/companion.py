"""Bounded in-memory relay for Companion Link state."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from racelens.object_storage import REPLAY_ID
from racelens.preparations import SESSION_ID

TTL_SECONDS = 7200
MAX_ACTIVE_LINKS = 512
MAX_TOMBSTONES = 512
MAX_REVISION = 2**63 - 1
LINK_ID = re.compile(r"^[A-Za-z0-9_-]{16,32}$")

RaceId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
DriverId = Annotated[str, StringConstraints(min_length=1, max_length=8, pattern=r"^[A-Z0-9]+$")]
Revision = Annotated[int, Field(ge=0, le=MAX_REVISION)]


class _FixedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CompanionState(_FixedModel):
    race_id: RaceId
    mode: Literal["replay", "live"]
    at_ms: Annotated[int | None, Field(ge=0, le=86_400_000)]
    selected_driver_ids: Annotated[list[DriverId], Field(max_length=2)]

    @field_validator("selected_driver_ids")
    @classmethod
    def drivers_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selected driver IDs must be unique")
        return value

    @model_validator(mode="after")
    def mode_matches_timestamp_and_race_id(self) -> CompanionState:
        if self.mode == "replay":
            if self.at_ms is None:
                raise ValueError("replay state requires at_ms")
            if not REPLAY_ID.fullmatch(self.race_id):
                raise ValueError("replay state requires a replay race ID")
        elif self.at_ms is not None:
            raise ValueError("live state requires a null at_ms")
        if not (REPLAY_ID.fullmatch(self.race_id) or SESSION_ID.fullmatch(self.race_id)):
            raise ValueError("invalid race ID")
        return self


class CompanionCreateRequest(_FixedModel):
    state: CompanionState


class CompanionPatchRequest(_FixedModel):
    expected_revision: Revision
    state: CompanionState


class CompanionSnapshot(_FixedModel):
    link_id: str
    revision: Revision
    expires_at: datetime
    state: CompanionState


class CompanionCreateResponse(CompanionSnapshot):
    secret: str


class CompanionRelayError(Exception):
    def __init__(self, code: Literal["not_found", "expired", "unauthorized", "conflict", "capacity"]):
        self.code = code
        super().__init__(code)


@dataclass(slots=True, repr=False)
class _Link:
    link_id: str
    secret_digest: bytes
    revision: int
    expires_monotonic: float
    expires_at: datetime
    state: CompanionState


class CompanionRelay:
    """Three-operation interface hiding auth, TTL, conflicts, and wakeups."""

    def __init__(
        self,
        *,
        max_links: int = MAX_ACTIVE_LINKS,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._max_links = max(1, min(max_links, MAX_ACTIVE_LINKS))
        self._clock = clock
        self._utcnow = utcnow
        self._links: dict[str, _Link] = {}
        self._expired: OrderedDict[str, None] = OrderedDict()
        self._changed = asyncio.Condition()

    async def create(self, state: CompanionState) -> CompanionCreateResponse:
        async with self._changed:
            now = self._clock()
            self._cleanup_expired(now)
            if len(self._links) >= self._max_links:
                raise CompanionRelayError("capacity")
            link_id = self._new_link_id()
            secret = secrets.token_urlsafe(32)
            expires_at = self._utcnow() + timedelta(seconds=TTL_SECONDS)
            link = _Link(
                link_id=link_id,
                secret_digest=self._digest(secret),
                revision=0,
                expires_monotonic=now + TTL_SECONDS,
                expires_at=expires_at,
                state=state.model_copy(deep=True),
            )
            self._links[link_id] = link
            return CompanionCreateResponse(
                **self._snapshot(link).model_dump(),
                secret=secret,
            )

    async def read(
        self,
        link_id: str,
        secret: str,
        *,
        after_revision: int,
        wait_seconds: float,
    ) -> CompanionSnapshot:
        deadline = self._clock() + wait_seconds
        async with self._changed:
            while True:
                now = self._clock()
                self._cleanup_expired(now)
                link = self._authorized(link_id, secret)
                if link.revision > after_revision:
                    return self._snapshot(link)
                remaining = min(deadline - now, link.expires_monotonic - now)
                if remaining <= 0:
                    if link.expires_monotonic <= now:
                        continue
                    return self._snapshot(link)
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=remaining)
                except TimeoutError:
                    pass

    async def replace(
        self,
        link_id: str,
        secret: str,
        *,
        expected_revision: int,
        state: CompanionState,
    ) -> CompanionSnapshot:
        async with self._changed:
            self._cleanup_expired(self._clock())
            link = self._authorized(link_id, secret)
            if link.revision != expected_revision:
                raise CompanionRelayError("conflict")
            link.revision += 1
            link.state = state.model_copy(deep=True)
            self._changed.notify_all()
            return self._snapshot(link)

    @staticmethod
    def _digest(secret: str) -> bytes:
        return hashlib.sha256(secret.encode()).digest()

    def _new_link_id(self) -> str:
        while True:
            link_id = secrets.token_urlsafe(12)
            if link_id not in self._links and link_id not in self._expired:
                return link_id

    def _authorized(self, link_id: str, secret: str) -> _Link:
        link = self._links.get(link_id)
        if link is None:
            raise CompanionRelayError("expired" if link_id in self._expired else "not_found")
        if not hmac.compare_digest(link.secret_digest, self._digest(secret)):
            raise CompanionRelayError("unauthorized")
        return link

    def _cleanup_expired(self, now: float) -> None:
        removed = False
        for link_id, link in tuple(self._links.items()):
            if link.expires_monotonic <= now:
                del self._links[link_id]
                self._expired[link_id] = None
                removed = True
        while len(self._expired) > MAX_TOMBSTONES:
            self._expired.popitem(last=False)
        if removed:
            self._changed.notify_all()

    @staticmethod
    def _snapshot(link: _Link) -> CompanionSnapshot:
        return CompanionSnapshot(
            link_id=link.link_id,
            revision=link.revision,
            expires_at=link.expires_at,
            state=link.state.model_copy(deep=True),
        )
