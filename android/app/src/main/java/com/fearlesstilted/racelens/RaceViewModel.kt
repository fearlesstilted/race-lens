package com.fearlesstilted.racelens

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ScreenState(
    val sessions: List<SessionSummary> = emptyList(),
    val live: LiveAvailability = LiveAvailability(false, "Checking Live…", null),
    val frame: WatchFrame = WatchFrame(),
    val feed: List<FeedItem> = emptyList(),
    val loading: Boolean = false,
    val message: String? = null,
)

class RaceViewModel(application: Application) : AndroidViewModel(application) {
    private val origin = DEFAULT_ORIGIN
    private var replayJob: Job? = null
    private var replayGeneration = 0L
    private var liveJob: Job? = null
    private var feedJob: Job? = null
    private var liveGeneration = 0L
    private var liveReconnects = 0
    private var lastLiveFeedAt = 0L
    private var foreground = true

    var state by mutableStateOf(ScreenState())
        private set

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            state = state.copy(loading = true, message = null)
            val api = RaceApi(origin)
            val sessions = withContext(Dispatchers.IO) { runCatching { api.sessions() } }
            val live = withContext(Dispatchers.IO) { runCatching { api.liveStatus() } }
            state = state.copy(
                sessions = sessions.getOrElse { state.sessions },
                live = live.getOrElse { LiveAvailability(false, "Live status unavailable", null) },
                loading = false,
                message = sessions.exceptionOrNull()?.let { "Replay catalog unavailable" },
            )
            if (state.frame.target.sessionId.isBlank()) recommendedReplayId(state.sessions)?.let(::chooseReplay)
            if (foreground && state.frame.target.mode == WatchMode.LIVE && state.live.available) startLiveStream()
        }
    }

    fun chooseReplay(sessionId: String) = navigate(WatchTarget(1, WatchMode.REPLAY, sessionId, 0, emptyList()))

    fun seek(atMs: Long) {
        val target = state.frame.target
        if (target.mode == WatchMode.REPLAY) navigate(target.copy(replayMs = atMs))
    }

    fun toggleDriver(driverId: String) {
        val focused = state.frame.target.focusedDrivers
        state = state.copy(frame = reduceWatch(state.frame, WatchAction.Focus(
            if (driverId in focused) focused - driverId else focused + driverId,
        )))
    }

    fun enterLive() {
        if (!state.live.available) {
            state = state.copy(message = state.live.detail)
            return
        }
        navigate(WatchTarget(1, WatchMode.LIVE, state.live.raceId ?: "live", null, emptyList()))
    }

    fun retry() = if (state.frame.target.mode == WatchMode.LIVE) startLiveStream() else {
        state.frame.target.takeIf { it.sessionId.isNotBlank() }?.let { loadReplay(it) }
    }

    fun handleDeepLink(raw: String) {
        parseWatchLink(raw)?.let(::navigate) ?: run {
            state = state.copy(message = "Invalid Race Lens Pocket link")
        }
    }

    fun onForeground() {
        foreground = true
        if (state.frame.target.mode == WatchMode.LIVE) startLiveStream()
        else if (shouldResumeReplay(state.loading, state.frame.snapshot)) loadReplay(state.frame.target)
    }

    fun onBackground() {
        foreground = false
        liveGeneration++
        liveJob?.cancel()
        liveJob = null
        replayGeneration++
        replayJob?.cancel()
        replayJob = null
        feedJob?.cancel()
        feedJob = null
    }

    private fun navigate(target: WatchTarget) {
        val next = target.normalized()
        if (next == state.frame.target && state.frame.snapshot != null) return
        liveGeneration++
        liveJob?.cancel()
        replayGeneration++
        replayJob?.cancel()
        feedJob?.cancel()
        val changedSession = next.sessionId != state.frame.target.sessionId || next.mode != state.frame.target.mode
        val frame = if (changedSession) reduceWatch(state.frame, WatchAction.Navigate(next)) else state.frame.copy(target = next, freshness = Freshness.FRESH)
        state = state.copy(frame = frame, feed = if (changedSession) emptyList() else state.feed, loading = next.mode == WatchMode.REPLAY, message = null)
        if (next.mode == WatchMode.REPLAY) loadReplay(next) else if (foreground) startLiveStream()
    }

    private fun loadReplay(target: WatchTarget) {
        if (target.sessionId.isBlank()) return
        replayJob?.cancel()
        val generation = ++replayGeneration
        replayJob = viewModelScope.launch {
            try {
                val api = RaceApi(origin)
                val timeline = withContext(Dispatchers.IO) { api.timeline(target.sessionId) }
                val atMs = (target.replayMs ?: 0).coerceIn(timeline.startMs.coerceAtLeast(0), timeline.endMs)
                val snapshot = withContext(Dispatchers.IO) { api.replayState(target.sessionId, atMs) }
                if (acceptsReplayCompletion(generation, replayGeneration, target, state.frame.target)) {
                    state = state.copy(frame = state.frame.copy(timeline = timeline, snapshot = snapshot), loading = false)
                    loadReplayFeed(generation, target, snapshot.atMs)
                }
            } catch (_: CancellationException) {
                throw CancellationException()
            } catch (error: Exception) {
                if (acceptsReplayCompletion(generation, replayGeneration, target, state.frame.target)) {
                    state = state.copy(loading = false, message = safeMessage(error))
                }
            }
        }
    }

    private fun startLiveStream() {
        if (!foreground || state.frame.target.mode != WatchMode.LIVE) return
        liveJob?.cancel()
        val generation = ++liveGeneration
        liveJob = viewModelScope.launch {
            state = state.copy(message = "Connecting to Live…", frame = state.frame.copy(timeline = null))
            while (foreground && generation == liveGeneration && state.frame.target.mode == WatchMode.LIVE && isActive) {
                val result = runCatching { withContext(Dispatchers.IO) {
                    RaceApi(origin).streamLive { snapshot -> viewModelScope.launch {
                        if (foreground && generation == liveGeneration && state.frame.target.mode == WatchMode.LIVE) {
                            liveReconnects = 0
                            state = state.copy(frame = state.frame.copy(snapshot = snapshot, freshness = Freshness.FRESH), message = null)
                            if (System.currentTimeMillis() - lastLiveFeedAt > 15_000) loadLiveFeed(generation, state.frame.target)
                        }
                    } }
                } }
                if (!foreground || generation != liveGeneration || state.frame.target.mode != WatchMode.LIVE) return@launch
                if (result.getOrNull() == LiveStreamResult.ENDED) {
                    val live = withContext(Dispatchers.IO) { runCatching { RaceApi(origin).liveStatus() } }.getOrNull()
                    if (!foreground || generation != liveGeneration || state.frame.target.mode != WatchMode.LIVE) return@launch
                    if (live?.status == "replay_ready" && live.replaySessionId != null) {
                        navigate(WatchTarget(1, WatchMode.REPLAY, live.replaySessionId, state.frame.snapshot?.atMs ?: 0, state.frame.target.focusedDrivers)); return@launch
                    }
                    if (live?.status in setOf("failed", "idle")) {
                        val stopped = requireNotNull(live)
                        state = state.copy(live = stopped, frame = state.frame.copy(freshness = Freshness.STALE), message = stopped.detail)
                        return@launch
                    }
                    state = state.copy(live = live ?: state.live, frame = state.frame.copy(freshness = Freshness.STALE), message = if (live?.status == "finishing") "Live ended; replay is preparing" else "Live connection closed")
                } else state = state.copy(frame = state.frame.copy(freshness = Freshness.STALE), message = "Live stale — ${result.exceptionOrNull()?.message ?: "connection closed"}")
                delay((1_000L shl liveReconnects.coerceAtMost(4)).coerceAtMost(15_000L))
                liveReconnects = (liveReconnects + 1).coerceAtMost(4)
            }
        }
    }

    private fun loadReplayFeed(generation: Long, target: WatchTarget, atMs: Long) {
        feedJob?.cancel()
        feedJob = viewModelScope.launch {
        val raceId = target.sessionId
        val items = withContext(Dispatchers.IO) { runCatching { RaceApi(origin).feed(raceId, atMs) } }.getOrNull() ?: return@launch
        if (generation == replayGeneration && target.replayIdentity() == state.frame.target.replayIdentity()) state = state.copy(feed = items)
        }
    }

    private fun loadLiveFeed(generation: Long, target: WatchTarget) {
        feedJob?.cancel()
        feedJob = viewModelScope.launch {
        lastLiveFeedAt = System.currentTimeMillis()
        val items = withContext(Dispatchers.IO) { runCatching { RaceApi(origin).liveFeed() } }.getOrNull() ?: return@launch
        if (foreground && generation == liveGeneration && target == state.frame.target && target.mode == WatchMode.LIVE) state = state.copy(feed = items)
        }
    }

    private fun safeMessage(error: Exception) = when (error) {
        is HttpStatusException -> "HTTP ${error.status}"
        else -> error.message?.take(120) ?: "Connection failed"
    }
}
