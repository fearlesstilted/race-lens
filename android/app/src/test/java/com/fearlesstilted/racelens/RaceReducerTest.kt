package com.fearlesstilted.racelens

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RaceReducerTest {
    private val replay = SharedRaceState("spa_2026_race", RaceMode.REPLAY, 12_000, emptyList())

    @Test
    fun remoteStateIsAppliedWithoutPublishingItBack() {
        val result = reduce(RaceModel(), RaceEvent.Remote(replay))

        assertEquals(replay, result.model.race)
        assertNull(result.publish)
    }

    @Test
    fun expiryAndDisconnectionRemainExplicit() {
        val linked = RaceModel(link = LinkState.LINKED)

        assertEquals(LinkState.EXPIRED, reduce(linked, RaceEvent.LinkExpired).model.link)
        assertEquals(LinkState.DISCONNECTED, reduce(linked, RaceEvent.LinkDisconnected).model.link)
    }

    @Test
    fun selectedDriverCanAlwaysBeDeselected() {
        val selected = reduce(RaceModel(race = replay), RaceEvent.Local(LocalAction.ToggleDriver("VER"))).model
        val deselected = reduce(selected, RaceEvent.Local(LocalAction.ToggleDriver("VER")))

        assertEquals(emptyList<String>(), deselected.model.race.selectedDriverIds)
        assertEquals(LocalAction.ToggleDriver("VER"), deselected.publish)
    }

    @Test
    fun onlyTwoUniqueDriversCanBeSelected() {
        var model = RaceModel(race = replay)
        model = reduce(model, RaceEvent.Local(LocalAction.ToggleDriver("VER"))).model
        model = reduce(model, RaceEvent.Local(LocalAction.ToggleDriver("NOR"))).model
        model = reduce(model, RaceEvent.Local(LocalAction.ToggleDriver("LEC"))).model

        assertEquals(listOf("VER", "NOR"), model.race.selectedDriverIds)
    }

    @Test
    fun conflictAppliesServerThenReappliesOneLocalActionOnce() {
        val local = LocalAction.Seek(42_000)
        val current = SharedRaceState("spa_2026_race", RaceMode.REPLAY, 20_000, listOf("NOR"))

        val result = resolveConflict(RaceModel(), current, local)
        val publish = requireNotNull(result.publish)

        assertEquals(42_000L, result.model.race.atMs)
        assertEquals(listOf("NOR"), result.model.race.selectedDriverIds)
        assertEquals(local, publish)
    }

    @Test
    fun navigationPublishesRaceModeAndTimeAtomically() {
        val live = RaceModel(SharedRaceState("live-123", RaceMode.LIVE, null, listOf("VER")))

        val result = reduce(
            live,
            RaceEvent.Local(LocalAction.Navigate("spa_2026_race", RaceMode.REPLAY, 0)),
        )

        assertEquals(SharedRaceState("spa_2026_race", RaceMode.REPLAY, 0, listOf("VER")), result.model.race)
        assertEquals(LocalAction.Navigate("spa_2026_race", RaceMode.REPLAY, 0), result.publish)
    }

    @Test
    fun olderCompanionRevisionIsRejected() {
        assertEquals(false, acceptsRevision(current = 4, incoming = 3))
        assertEquals(false, acceptsRevision(current = 4, incoming = 4))
        assertEquals(true, acceptsRevision(current = 4, incoming = 5))
    }

    @Test
    fun catalogDefaultsOnlyWhileFullyDisconnected() {
        assertEquals(true, shouldDefaultReplay("", LinkState.DISCONNECTED))
        assertEquals(false, shouldDefaultReplay("", LinkState.RECONNECTING))
        assertEquals(false, shouldDefaultReplay("", LinkState.LINKED))
        assertEquals(false, shouldDefaultReplay("chosen", LinkState.DISCONNECTED))
    }

    @Test
    fun replayCompletionMustMatchLatestGenerationAndRace() {
        val current = SharedRaceState("spa_2026_race", RaceMode.REPLAY, 0, emptyList())

        assertEquals(true, acceptsReplayCompletion(2, 2, "spa_2026_race", current))
        assertEquals(false, acceptsReplayCompletion(1, 2, "spa_2026_race", current))
        assertEquals(false, acceptsReplayCompletion(2, 2, "monza_2026_race", current))
        assertEquals(false, acceptsReplayCompletion(2, 2, "spa_2026_race", current.copy(mode = RaceMode.LIVE)))
    }

    @Test
    fun appLinkParserAcceptsVerifiedShapeAndKeepsTokenOutOfSafeUrl() {
        val link = parseCompanionLink("https://race-lens.onrender.com/companion/abc-123#token=s3cr3t")

        assertEquals("abc-123", link?.id)
        assertEquals("s3cr3t", link?.token)
        assertEquals("https://race-lens.onrender.com/companion/abc-123", link?.safeUrl)
    }
}
