package com.fearlesstilted.racelens

import java.net.URI

private val sessionIdPattern = Regex("^[a-z0-9][a-z0-9_-]{0,79}$")
private val driverIdPattern = Regex("^[A-Z0-9]{2,5}$")

enum class WatchMode { REPLAY, LIVE }
enum class Freshness { FRESH, STALE }

data class WatchTarget(
    val version: Int,
    val mode: WatchMode,
    val sessionId: String,
    val replayMs: Long?,
    val focusedDrivers: List<String>,
)

data class WatchFrame(
    val target: WatchTarget = WatchTarget(1, WatchMode.REPLAY, "", 0, emptyList()),
    val timeline: Timeline? = null,
    val snapshot: RaceSnapshot? = null,
    val freshness: Freshness = Freshness.FRESH,
)

sealed interface WatchAction {
    data class Navigate(val target: WatchTarget) : WatchAction
    data class Focus(val drivers: List<String>) : WatchAction
}

fun reduceWatch(frame: WatchFrame, action: WatchAction): WatchFrame = when (action) {
    is WatchAction.Navigate -> frame.copy(
        target = action.target.normalized(),
        timeline = null,
        snapshot = null,
        freshness = Freshness.FRESH,
    )
    is WatchAction.Focus -> frame.copy(target = frame.target.copy(focusedDrivers = action.drivers.focused()))
}

fun acceptsReplayCompletion(generation: Long, currentGeneration: Long, requested: WatchTarget, current: WatchTarget) =
    generation == currentGeneration && requested.replayIdentity() == current.replayIdentity() && current.mode == WatchMode.REPLAY

fun shouldResumeReplay(loading: Boolean, snapshot: RaceSnapshot?) = loading || snapshot == null

fun recommendedReplayId(sessions: List<SessionSummary>): String? = sessions.map { it.id }.firstOrNull { it == "hungarian_2026_race" }
    ?: sessions.map { it.id }.firstOrNull { it == "bahrain_2021_race" }
    ?: sessions.map { it.id }.firstOrNull { it.endsWith("_race") }

fun parseWatchLink(raw: String): WatchTarget? = runCatching {
    val uri = URI(raw)
    val https = uri.scheme == "https" && uri.host == "race-lens.onrender.com" && uri.path == "/pocket"
    val app = uri.scheme == "racelens" && uri.host == "pocket" && uri.path.isEmpty()
    if (!https && !app) return null
    val query = uri.rawQuery.orEmpty().split('&').associate {
        val (key, value) = it.split('=', limit = 2).let { pair -> pair[0] to pair.getOrElse(1) { "" } }
        java.net.URLDecoder.decode(key, Charsets.UTF_8) to java.net.URLDecoder.decode(value, Charsets.UTF_8)
    }
    val mode = when (query["mode"]) {
        "replay" -> WatchMode.REPLAY
        "live" -> WatchMode.LIVE
        else -> return null
    }
    val version = query["v"]?.toIntOrNull() ?: return null
    val sessionId = query["session"]?.trim().orEmpty()
    if (version != 1 || !sessionIdPattern.matches(sessionId)) return null
    val replayMs = query["at"]?.toLongOrNull()?.takeIf { it >= 0 }
    if ((mode == WatchMode.LIVE && replayMs != null) || (mode == WatchMode.REPLAY && replayMs == null)) return null
    WatchTarget(version, mode, sessionId, replayMs, query["drivers"].orEmpty().split(',').focused()).normalized()
}.getOrNull()

fun WatchTarget.normalized() = copy(
    sessionId = sessionId.trim(),
    replayMs = if (mode == WatchMode.LIVE) null else (replayMs ?: 0).coerceAtLeast(0),
    focusedDrivers = focusedDrivers.focused(),
)

private fun List<String>.focused() = map(String::trim).filter(driverIdPattern::matches).distinct().take(2)
fun WatchTarget.replayIdentity() = listOf(version, mode, sessionId, replayMs)
