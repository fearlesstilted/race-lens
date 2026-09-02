package com.fearlesstilted.racelens

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RaceReducerTest {
    @Test
    fun appLinkParsesOneShotReplayHandoff() {
        val target = parseWatchLink(
            "https://race-lens.onrender.com/pocket?v=1&mode=replay&session=spa_2026_race&at=12000&drivers=VER,NOR",
        )

        assertEquals(WatchTarget(1, WatchMode.REPLAY, "spa_2026_race", 12_000, listOf("VER", "NOR")), target)
    }

    @Test
    fun appLinkRejectsInvalidHostAndLiveReplayTime() {
        assertNull(parseWatchLink("https://example.com/pocket?v=1&mode=live&session=live"))
        assertNull(parseWatchLink("https://race-lens.onrender.com/pocket?v=1&mode=live&session=live&at=3"))
    }

    @Test
    fun navigationClearsFrameAndLimitsFocusToTwoDrivers() {
        val current = WatchFrame(
            WatchTarget(1, WatchMode.REPLAY, "spa_2026_race", 1_000, listOf("VER")),
            snapshot = RaceSnapshot(1_000, 1, "green", emptyList()),
        )
        val moved = reduceWatch(current, WatchAction.Navigate(WatchTarget(1, WatchMode.LIVE, "live", null, emptyList())))

        assertNull(moved.snapshot)
        assertNull(moved.timeline)
        assertEquals(WatchMode.LIVE, moved.target.mode)
        assertEquals(listOf("NOR", "LEC"), reduceWatch(moved, WatchAction.Focus(listOf("NOR", "LEC", "VER", "NOR"))).target.focusedDrivers)
    }

    @Test
    fun staleReplayCompletionCannotReplaceNewTarget() {
        val target = WatchTarget(1, WatchMode.REPLAY, "spa_2026_race", 0, emptyList())
        assertEquals(true, acceptsReplayCompletion(2, 2, target, target))
        assertEquals(false, acceptsReplayCompletion(1, 2, target, target))
        assertEquals(false, acceptsReplayCompletion(2, 2, target, target.copy(sessionId = "monza_2026_race")))
    }

    @Test
    fun focusChangesDuringReplaySeekDoNotInvalidateTheRequestedFrame() {
        val requested = WatchTarget(1, WatchMode.REPLAY, "spa_2026_race", 12_000, listOf("VER"))
        assertEquals(true, acceptsReplayCompletion(2, 2, requested, requested.copy(focusedDrivers = listOf("NOR", "LEC"))))
    }

    @Test
    fun foregroundResumesAnInterruptedReplayLoad() {
        assertEquals(true, shouldResumeReplay(loading = true, snapshot = RaceSnapshot(1, 1, "green", emptyList())))
        assertEquals(true, shouldResumeReplay(loading = false, snapshot = null))
        assertEquals(false, shouldResumeReplay(loading = false, snapshot = RaceSnapshot(1, 1, "green", emptyList())))
    }

    @Test
    fun recommendationMatchesTheWebRaceOrder() {
        val sessions = listOf(
            SessionSummary("monaco_2024_practice", "fixture"),
            SessionSummary("bahrain_2021_race", "fixture"),
            SessionSummary("hungarian_2026_race", "fixture"),
        )
        assertEquals("hungarian_2026_race", recommendedReplayId(sessions))
        assertEquals("bahrain_2021_race", recommendedReplayId(sessions.dropLast(1)))
        assertEquals(null, recommendedReplayId(listOf(SessionSummary("spa_2026_practice", "fixture"))))
    }

    @Test
    fun appUriParsesButHttpsRemainsTheBrowserFallback() {
        assertEquals(
            WatchTarget(1, WatchMode.LIVE, "2026-16-r", null, listOf("VER", "NOR")),
            parseWatchLink("racelens://pocket?v=1&mode=live&session=2026-16-r&drivers=VER,NOR"),
        )
    }

    @Test
    fun jsonNullDoesNotBecomeVisibleText() {
        assertNull(nullableJsonString(Any()))
        assertEquals("Dutch Grand Prix", nullableJsonString(" Dutch Grand Prix "))
    }

    @Test
    fun replayReadyIsNotPresentedAsStillPreparing() {
        assertEquals("Live ended; replay is preparing", liveStatusDetail("finishing", false, null))
        assertEquals("Live ended; replay ready", liveStatusDetail("replay_ready", false, null))
    }

    @Test
    fun feedKeepsRecentEventsAndTheNewestRadio() {
        val items = (1..6).map { index ->
            FeedItem("$index", "Event $index", index, if (index == 5) "https://livetiming.formula1.com/static/radio.mp3" else null)
        }

        assertEquals(listOf("1", "2", "3", "5"), visibleFeedItems(items).map(FeedItem::id))
    }

    @Test
    fun focusShowsWhichSelectedDriverHasTheGapAdvantage() {
        val verstappen = DriverTiming("VER", 4, 16.928, 2.1, "SOFT", 18, 55)
        val norris = DriverTiming("NOR", 1, null, null, "HARD", 18, 56)

        assertEquals(FocusEdge("NOR", 16.928), focusEdge(listOf(verstappen, norris)))
        assertEquals(FocusEdge(null, 0.0), focusEdge(listOf(norris, norris.copy(id = "PIA"))))
        assertNull(focusEdge(listOf(verstappen, norris.copy(id = "PIA", position = 2, gapSeconds = null))))
    }
}
