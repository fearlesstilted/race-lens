package com.fearlesstilted.racelens

import java.net.URI

enum class RaceMode { REPLAY, LIVE }
enum class LinkState { LINKED, RECONNECTING, EXPIRED, DISCONNECTED }

data class SharedRaceState(
    val raceId: String,
    val mode: RaceMode,
    val atMs: Long?,
    val selectedDriverIds: List<String>,
)

data class RaceModel(
    val race: SharedRaceState = SharedRaceState("", RaceMode.REPLAY, 0, emptyList()),
    val link: LinkState = LinkState.DISCONNECTED,
)

sealed interface LocalAction {
    data class Navigate(val raceId: String, val mode: RaceMode, val atMs: Long?) : LocalAction
    data class Seek(val atMs: Long) : LocalAction
    data class ToggleDriver(val driverId: String) : LocalAction
}

sealed interface RaceEvent {
    data class Local(val action: LocalAction) : RaceEvent
    data class Remote(val state: SharedRaceState) : RaceEvent
    data object LinkExpired : RaceEvent
    data object LinkDisconnected : RaceEvent
    data object LinkReconnecting : RaceEvent
}

data class Reduction(val model: RaceModel, val publish: LocalAction? = null)

fun reduce(model: RaceModel, event: RaceEvent): Reduction = when (event) {
    is RaceEvent.Remote -> Reduction(model.copy(race = event.state.normalized(), link = LinkState.LINKED))
    RaceEvent.LinkExpired -> Reduction(model.copy(link = LinkState.EXPIRED))
    RaceEvent.LinkDisconnected -> Reduction(model.copy(link = LinkState.DISCONNECTED))
    RaceEvent.LinkReconnecting -> Reduction(model.copy(link = LinkState.RECONNECTING))
    is RaceEvent.Local -> applyLocal(model, event.action)
}

private fun applyLocal(model: RaceModel, action: LocalAction): Reduction {
    val current = model.race
    val next = when (action) {
        is LocalAction.Navigate -> current.copy(
            raceId = action.raceId,
            mode = action.mode,
            atMs = action.atMs,
        )
        is LocalAction.Seek -> current.copy(atMs = action.atMs.coerceAtLeast(0))
        is LocalAction.ToggleDriver -> {
            val selected = current.selectedDriverIds
            when {
                action.driverId in selected -> current.copy(selectedDriverIds = selected - action.driverId)
                selected.size < 2 -> current.copy(selectedDriverIds = selected + action.driverId)
                else -> current
            }
        }
    }.normalized()
    return if (next == current) Reduction(model) else {
        val updated = model.copy(race = next)
        Reduction(updated, action)
    }
}

fun acceptsRevision(current: Long, incoming: Long) = incoming > current

fun shouldDefaultReplay(raceId: String, link: LinkState) =
    raceId.isBlank() && link == LinkState.DISCONNECTED

fun acceptsReplayCompletion(
    generation: Long,
    currentGeneration: Long,
    raceId: String,
    current: SharedRaceState,
) = generation == currentGeneration && current.mode == RaceMode.REPLAY && current.raceId == raceId

fun resolveConflict(model: RaceModel, serverState: SharedRaceState, action: LocalAction): Reduction {
    val remote = reduce(model, RaceEvent.Remote(serverState)).model
    return applyLocal(remote, action)
}

private fun SharedRaceState.normalized() = copy(
    atMs = if (mode == RaceMode.LIVE) null else (atMs ?: 0).coerceAtLeast(0),
    selectedDriverIds = selectedDriverIds.distinct().take(2),
)

data class CompanionLink(val id: String, val token: String, val origin: String, val safeUrl: String)

fun parseCompanionLink(raw: String): CompanionLink? = runCatching {
    val uri = URI(raw)
    if (uri.scheme != "https" || uri.host != "race-lens.onrender.com") return null
    val parts = uri.path.trim('/').split('/')
    if (parts.size != 2 || parts[0] != "companion" || parts[1].isBlank()) return null
    val token = uri.rawFragment
        ?.split('&')
        ?.firstOrNull { it.startsWith("token=") }
        ?.substringAfter("token=")
        ?.takeIf(String::isNotBlank)
        ?: return null
    CompanionLink(parts[1], token, "https://${uri.host}", "https://${uri.host}${uri.path}")
}.getOrNull()
