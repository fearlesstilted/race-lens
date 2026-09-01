package com.fearlesstilted.racelens

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

const val DEFAULT_ORIGIN = "https://race-lens.onrender.com"

data class SessionSummary(val id: String, val source: String)
data class Timeline(val startMs: Long, val endMs: Long)
data class DriverTiming(
    val id: String,
    val position: Int?,
    val gapSeconds: Double?,
    val intervalSeconds: Double?,
    val tyre: String?,
    val tyreAge: Int?,
    val laps: Int,
)
data class RaceSnapshot(val atMs: Long, val lap: Int, val status: String, val drivers: List<DriverTiming>)
data class LiveAvailability(val available: Boolean, val detail: String, val raceId: String?)
data class CompanionSnapshot(val revision: Long, val state: SharedRaceState)

class HttpStatusException(val status: Int, message: String) : Exception(message)

fun validatedOrigin(value: String): String? = runCatching {
    val uri = URI(value.trim())
    val local = uri.host in setOf("localhost", "127.0.0.1", "10.0.2.2", "::1")
    if (uri.host == null || uri.userInfo != null || uri.query != null || uri.fragment != null) return null
    if (uri.scheme != "https" && !(uri.scheme == "http" && local)) return null
    "${uri.scheme}://${uri.rawAuthority}${uri.path.trimEnd('/')}"
}.getOrNull()

class RaceApi(private val origin: String) {
    fun sessions(): List<SessionSummary> = getJson("/api/sessions").let { array ->
        List(array.length()) { index ->
            val item = array.getJSONObject(index)
            SessionSummary(item.getString("session_id"), item.optString("source", "unknown"))
        }
    }

    fun timeline(raceId: String): Timeline = getObject("/api/sessions/${encoded(raceId)}/timeline").let {
        Timeline(it.getLong("start_ms"), it.getLong("end_ms"))
    }

    fun replayState(raceId: String, atMs: Long): RaceSnapshot = parseRaceState(
        getObject("/api/sessions/${encoded(raceId)}/state?at_ms=${atMs.coerceAtLeast(0)}")
    )

    fun liveStatus(): LiveAvailability {
        val body = getObject("/api/live/status")
        val status = body.optString("status", if (body.optBoolean("is_running")) "live" else "idle")
        val available = body.optBoolean("is_running") || status == "live"
        val detail = when {
            status == "failed" -> body.optString("failure", "Live failed")
            available -> "Live timing active"
            status == "finishing" || status == "replay_ready" -> "Live ended; replay is preparing"
            else -> "No live session"
        }
        return LiveAvailability(available, detail, body.optString("canonical_session_id").takeIf { it.isNotBlank() })
    }

    fun streamLive(onState: (RaceSnapshot) -> Unit) {
        val connection = open("/api/live/stream?tick_s=2")
        connection.readTimeout = 35_000
        checkResponse(connection)
        connection.inputStream.bufferedReader().use { reader ->
            while (true) {
                val line = reader.readLine() ?: break
                if (line.startsWith("data:")) {
                    val payload = line.substringAfter("data:").trim()
                    if (payload != "{}") onState(parseRaceState(JSONObject(payload)))
                }
                if (line == "event: end") break
            }
        }
        connection.disconnect()
    }

    private fun getObject(path: String): JSONObject = JSONObject(request(path))
    private fun getJson(path: String): JSONArray = JSONArray(request(path))

    private fun request(path: String): String {
        val connection = open(path)
        return try {
            checkResponse(connection)
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun open(path: String) = (URL(origin + path).openConnection() as HttpURLConnection).apply {
        connectTimeout = 8_000
        readTimeout = 30_000
        setRequestProperty("Accept", "application/json, text/event-stream")
    }
}

class CompanionApi(private val link: CompanionLink) {
    fun poll(afterRevision: Long, waitSeconds: Int = 25): CompanionSnapshot = response(
        path = "/api/companion-links/${encoded(link.id)}?after_revision=$afterRevision&wait_seconds=$waitSeconds",
    )

    fun patch(expectedRevision: Long, state: SharedRaceState): CompanionSnapshot = response(
        path = "/api/companion-links/${encoded(link.id)}",
        method = "PATCH",
        body = JSONObject().put("expected_revision", expectedRevision).put("state", state.toJson()).toString(),
    )

    private fun response(path: String, method: String = "GET", body: String? = null): CompanionSnapshot {
        val connection = (URL(link.origin + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 8_000
            readTimeout = 30_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer ${link.token}")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toByteArray(StandardCharsets.UTF_8)) }
            }
        }
        return try {
            checkResponse(connection)
            val json = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            CompanionSnapshot(json.getLong("revision"), json.getJSONObject("state").toSharedState())
        } finally {
            connection.disconnect()
        }
    }
}

private fun SharedRaceState.toJson() = JSONObject()
    .put("race_id", raceId)
    .put("mode", mode.name.lowercase())
    .put("at_ms", atMs ?: JSONObject.NULL)
    .put("selected_driver_ids", JSONArray(selectedDriverIds))

private fun JSONObject.toSharedState(): SharedRaceState {
    val selected = getJSONArray("selected_driver_ids")
    return SharedRaceState(
        raceId = getString("race_id"),
        mode = if (getString("mode") == "live") RaceMode.LIVE else RaceMode.REPLAY,
        atMs = if (isNull("at_ms")) null else getLong("at_ms"),
        selectedDriverIds = List(selected.length()) { selected.getString(it) }.distinct().take(2),
    )
}

private fun parseRaceState(json: JSONObject): RaceSnapshot {
    val order = json.optJSONArray("classification") ?: JSONArray()
    val drivers = json.optJSONObject("drivers") ?: JSONObject()
    return RaceSnapshot(
        atMs = json.optLong("at_ms"),
        lap = json.optInt("lap"),
        status = json.optString("session_status", "unknown"),
        drivers = List(order.length()) { index ->
            val id = order.getString(index)
            val driver = drivers.optJSONObject(id) ?: JSONObject()
            DriverTiming(
                id = id,
                position = driver.optNullableInt("rank") ?: driver.optNullableInt("position"),
                gapSeconds = driver.optNullableDouble("gap_s"),
                intervalSeconds = driver.optNullableDouble("interval_s"),
                tyre = driver.optString("tyre_compound").takeIf { it.isNotBlank() },
                tyreAge = driver.optNullableInt("tyre_age_laps"),
                laps = driver.optInt("laps_completed"),
            )
        },
    )
}

private fun JSONObject.optNullableInt(name: String) = if (isNull(name) || !has(name)) null else optInt(name)
private fun JSONObject.optNullableDouble(name: String) = if (isNull(name) || !has(name)) null else optDouble(name)
private fun encoded(value: String) = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

private fun checkResponse(connection: HttpURLConnection) {
    val status = connection.responseCode
    if (status !in 200..299) {
        val detail = connection.errorStream?.bufferedReader()?.use(BufferedReader::readText)?.take(200)
        throw HttpStatusException(status, detail ?: "HTTP $status")
    }
}
