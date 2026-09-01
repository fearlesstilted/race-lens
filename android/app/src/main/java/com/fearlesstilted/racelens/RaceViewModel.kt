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
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.IOException

data class ScreenState(
    val origin: String = DEFAULT_ORIGIN,
    val originInput: String = DEFAULT_ORIGIN,
    val sessions: List<SessionSummary> = emptyList(),
    val timeline: Timeline? = null,
    val snapshot: RaceSnapshot? = null,
    val live: LiveAvailability = LiveAvailability(false, "Checking Live…", null),
    val race: RaceModel = RaceModel(),
    val loading: Boolean = false,
    val message: String? = null,
)

class RaceViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("race_lens", 0)
    private val syncMutex = Mutex()
    private var companionApi: CompanionApi? = null
    private var companionRevision = -1L
    private var companionState: SharedRaceState? = null
    private var companionJob: Job? = null
    private var companionGeneration = 0L
    private var replayJob: Job? = null
    private var replayGeneration = 0L
    private var liveJob: Job? = null
    private var liveGeneration = 0L

    var state by mutableStateOf(
        ScreenState(
            origin = preferences.getString("origin", DEFAULT_ORIGIN) ?: DEFAULT_ORIGIN,
            originInput = preferences.getString("origin", DEFAULT_ORIGIN) ?: DEFAULT_ORIGIN,
        )
    )
        private set

    init { refresh() }

    fun setOriginInput(value: String) { state = state.copy(originInput = value) }

    fun saveOrigin() {
        val origin = validatedOrigin(state.originInput)
        if (origin == null) {
            state = state.copy(message = "Use HTTPS, or HTTP only for localhost / 10.0.2.2")
            return
        }
        preferences.edit().putString("origin", origin).apply()
        state = state.copy(origin = origin, originInput = origin, message = null)
        refresh()
    }

    fun refresh() {
        liveGeneration++
        liveJob?.cancel()
        viewModelScope.launch {
            state = state.copy(loading = true, message = null)
            val api = RaceApi(state.origin)
            val sessionsResult = withContext(Dispatchers.IO) { runCatching { api.sessions() } }
            val liveResult = withContext(Dispatchers.IO) { runCatching { api.liveStatus() } }
            val sessions = sessionsResult.getOrElse { state.sessions }
            val live = liveResult.getOrElse { LiveAvailability(false, "Live status unavailable", null) }
            state = state.copy(
                sessions = sessions,
                live = live,
                loading = false,
                message = if (sessionsResult.isFailure) "Replay catalog unavailable" else null,
            )
            if (shouldDefaultReplay(state.race.race.raceId, state.race.link) && sessions.isNotEmpty()) {
                chooseRace(sessions.first().id)
            }
            else if (state.race.race.mode == RaceMode.LIVE && live.available) startLiveStream()
        }
    }

    fun chooseRace(raceId: String) {
        dispatch(LocalAction.Navigate(raceId, RaceMode.REPLAY, 0))
        loadReplay(raceId, 0)
    }

    fun seek(atMs: Long) {
        dispatch(LocalAction.Seek(atMs))
        loadReplay(state.race.race.raceId, atMs)
    }

    fun toggleDriver(driverId: String) = dispatch(LocalAction.ToggleDriver(driverId))

    fun enterLive() {
        if (!state.live.available) {
            state = state.copy(message = state.live.detail)
            return
        }
        val raceId = state.live.raceId ?: "live"
        dispatch(LocalAction.Navigate(raceId, RaceMode.LIVE, null))
        startLiveStream()
    }

    fun handleDeepLink(raw: String) {
        val link = parseCompanionLink(raw)
        if (link == null) {
            state = state.copy(message = "Invalid Companion Link")
            return
        }
        leaveCompanion()
        val api = CompanionApi(link)
        val generation = ++companionGeneration
        companionApi = api
        companionRevision = -1
        companionState = null
        state = state.copy(race = state.race.copy(link = LinkState.RECONNECTING), message = null)
        companionJob = viewModelScope.launch { pollCompanion(api, generation) }
    }

    fun leaveCompanion() {
        companionGeneration++
        companionJob?.cancel()
        companionJob = null
        companionApi = null
        companionRevision = -1
        companionState = null
        state = state.copy(race = state.race.copy(link = LinkState.DISCONNECTED))
    }

    private fun dispatch(action: LocalAction) {
        val result = reduce(state.race, RaceEvent.Local(action))
        state = state.copy(race = result.model)
        val api = companionApi
        val generation = companionGeneration
        if (api != null && (result.publish != null || companionRevision < 0)) {
            viewModelScope.launch { publish(action, api, generation) }
        }
    }

    private fun loadReplay(raceId: String, requestedMs: Long) {
        if (raceId.isBlank()) return
        liveGeneration++
        liveJob?.cancel()
        replayJob?.cancel()
        val generation = ++replayGeneration
        replayJob = viewModelScope.launch {
            state = state.copy(loading = true, message = null)
            try {
                val api = RaceApi(state.origin)
                val timeline = withContext(Dispatchers.IO) { api.timeline(raceId) }
                if (!acceptsReplayCompletion(generation, replayGeneration, raceId, state.race.race)) return@launch
                val atMs = requestedMs.coerceIn(timeline.startMs.coerceAtLeast(0), timeline.endMs)
                val snapshot = withContext(Dispatchers.IO) { api.replayState(raceId, atMs) }
                if (!acceptsReplayCompletion(generation, replayGeneration, raceId, state.race.race)) return@launch
                state = state.copy(timeline = timeline, snapshot = snapshot, loading = false)
            } catch (_: CancellationException) {
                throw CancellationException()
            } catch (error: Exception) {
                if (acceptsReplayCompletion(generation, replayGeneration, raceId, state.race.race)) {
                    state = state.copy(loading = false, message = safeMessage(error))
                }
            }
        }
    }

    private fun startLiveStream() {
        replayGeneration++
        replayJob?.cancel()
        liveJob?.cancel()
        val generation = ++liveGeneration
        liveJob = viewModelScope.launch {
            state = state.copy(message = "Connecting to Live…", timeline = null)
            try {
                withContext(Dispatchers.IO) {
                    RaceApi(state.origin).streamLive { snapshot ->
                        viewModelScope.launch {
                            if (generation == liveGeneration && state.race.race.mode == RaceMode.LIVE) {
                                state = state.copy(snapshot = snapshot, message = null)
                            }
                        }
                    }
                }
                if (isActive && generation == liveGeneration) state = state.copy(message = "Live stream ended")
            } catch (_: CancellationException) {
                throw CancellationException()
            } catch (error: Exception) {
                if (generation == liveGeneration) {
                    state = state.copy(message = "Live unavailable: ${safeMessage(error)}")
                }
            }
        }
    }

    private suspend fun pollCompanion(api: CompanionApi, generation: Long) {
        while (currentCoroutineContext().isActive) {
            if (!isCurrentCompanion(api, generation)) return
            try {
                val afterRevision = syncMutex.withLock {
                    if (!isCurrentCompanion(api, generation)) return
                    companionRevision
                }
                if (!isCurrentCompanion(api, generation)) return
                val remote = withContext(Dispatchers.IO) { api.poll(afterRevision) }
                if (!isCurrentCompanion(api, generation)) return
                syncMutex.withLock {
                    if (isCurrentCompanion(api, generation)) admitSnapshot(remote, apply = true)
                }
            } catch (error: HttpStatusException) {
                if (!isCurrentCompanion(api, generation)) return
                when (error.status) {
                    410 -> setLink(RaceEvent.LinkExpired)
                    404, 401 -> setLink(RaceEvent.LinkDisconnected)
                    else -> reconnect()
                }
                if (error.status in setOf(410, 404, 401)) {
                    companionApi = null
                    return
                }
            } catch (_: IOException) {
                if (!isCurrentCompanion(api, generation)) return
                reconnect()
            }
        }
    }

    private suspend fun publish(action: LocalAction, api: CompanionApi, generation: Long) = syncMutex.withLock {
        if (!isCurrentCompanion(api, generation)) return@withLock
        try {
            if (companionState == null) {
                if (!isCurrentCompanion(api, generation)) return@withLock
                val initial = withContext(Dispatchers.IO) { api.poll(-1, 0) }
                if (!isCurrentCompanion(api, generation)) return@withLock
                if (!admitSnapshot(initial, apply = false)) return@withLock
            }
            val reapplied = resolveConflict(state.race, companionState ?: return@withLock, action)
            applyRemote(reapplied.model.race)
            if (!isCurrentCompanion(api, generation)) return@withLock
            val result = withContext(Dispatchers.IO) { api.patch(companionRevision, reapplied.model.race) }
            if (!isCurrentCompanion(api, generation)) return@withLock
            admitSnapshot(result, apply = false)
        } catch (conflict: HttpStatusException) {
            if (!isCurrentCompanion(api, generation)) return@withLock
            if (conflict.status != 409) {
                handlePublishFailure(conflict)
                return@withLock
            }
            try {
                if (!isCurrentCompanion(api, generation)) return@withLock
                val current = withContext(Dispatchers.IO) { api.poll(companionRevision, 0) }
                if (!isCurrentCompanion(api, generation)) return@withLock
                if (!admitSnapshot(current, apply = false)) return@withLock
                val reapplied = resolveConflict(state.race, current.state, action)
                applyRemote(reapplied.model.race)
                if (!isCurrentCompanion(api, generation)) return@withLock
                val result = withContext(Dispatchers.IO) { api.patch(companionRevision, reapplied.model.race) }
                if (!isCurrentCompanion(api, generation)) return@withLock
                admitSnapshot(result, apply = false)
            } catch (secondFailure: Exception) {
                if (isCurrentCompanion(api, generation)) handlePublishFailure(secondFailure)
            }
        } catch (error: Exception) {
            if (isCurrentCompanion(api, generation)) handlePublishFailure(error)
        }
    }

    private fun isCurrentCompanion(api: CompanionApi, generation: Long) =
        companionApi === api && companionGeneration == generation

    private fun applyRemote(remote: SharedRaceState) {
        val previous = state.race.race
        val result = reduce(state.race, RaceEvent.Remote(remote))
        state = state.copy(race = result.model, message = null)
        if (remote.mode == RaceMode.LIVE && remote != previous) {
            viewModelScope.launch {
                val live = runCatching { withContext(Dispatchers.IO) { RaceApi(state.origin).liveStatus() } }.getOrNull()
                if (live?.available == true) {
                    state = state.copy(live = live)
                    startLiveStream()
                } else state = state.copy(message = live?.detail ?: "Live unavailable")
            }
        } else if (remote != previous) loadReplay(remote.raceId, remote.atMs ?: 0)
    }

    private suspend fun reconnect() {
        setLink(RaceEvent.LinkReconnecting)
        delay(1_000)
    }

    private fun handlePublishFailure(error: Exception) {
        when ((error as? HttpStatusException)?.status) {
            410 -> setLink(RaceEvent.LinkExpired)
            404, 401 -> setLink(RaceEvent.LinkDisconnected)
            else -> setLink(RaceEvent.LinkReconnecting)
        }
    }

    private fun setLink(event: RaceEvent) { state = state.copy(race = reduce(state.race, event).model) }
    private fun admitSnapshot(snapshot: CompanionSnapshot, apply: Boolean): Boolean {
        if (snapshot.revision < companionRevision) return false
        if (!acceptsRevision(companionRevision, snapshot.revision)) {
            state = state.copy(race = state.race.copy(link = LinkState.LINKED), message = null)
            return false
        }
        companionRevision = snapshot.revision
        companionState = snapshot.state
        if (apply) applyRemote(snapshot.state)
        else state = state.copy(race = state.race.copy(link = LinkState.LINKED), message = null)
        return true
    }
    private fun safeMessage(error: Exception) = when (error) {
        is HttpStatusException -> "HTTP ${error.status}"
        else -> error.message?.take(120) ?: "Connection failed"
    }
}
