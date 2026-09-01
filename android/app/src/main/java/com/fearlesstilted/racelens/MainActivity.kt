package com.fearlesstilted.racelens

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

class MainActivity : ComponentActivity() {
    private val viewModel: RaceViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        consumeDeepLink(intent)
        setContent { RaceLensApp(viewModel) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        consumeDeepLink(intent)
        setIntent(Intent(this, MainActivity::class.java))
    }

    private fun consumeDeepLink(intent: Intent?) {
        val raw = intent?.data?.toString() ?: return
        intent.data = null
        viewModel.handleDeepLink(raw)
    }
}

private val Ink = Color(0xFF090D12)
private val Panel = Color(0xFF141A22)
private val Signal = Color(0xFFFF4D35)
private val Mint = Color(0xFF61E7B5)
private val Muted = Color(0xFF9BA8B8)

@Composable
fun RaceLensApp(viewModel: RaceViewModel) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Signal,
            secondary = Mint,
            background = Ink,
            surface = Panel,
        )
    ) {
        RaceScreen(
            state = viewModel.state,
            setOrigin = viewModel::setOriginInput,
            saveOrigin = viewModel::saveOrigin,
            refresh = viewModel::refresh,
            chooseRace = viewModel::chooseRace,
            enterLive = viewModel::enterLive,
            seek = viewModel::seek,
            toggleDriver = viewModel::toggleDriver,
            leave = viewModel::leaveCompanion,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RaceScreen(
    state: ScreenState,
    setOrigin: (String) -> Unit,
    saveOrigin: () -> Unit,
    refresh: () -> Unit,
    chooseRace: (String) -> Unit,
    enterLive: () -> Unit,
    seek: (Long) -> Unit,
    toggleDriver: (String) -> Unit,
    leave: () -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Ink),
                title = {
                    Column {
                        Text("RACE LENS", fontWeight = FontWeight.Black, letterSpacing = 2.sp)
                        Text(
                            "POCKET  •  Companion: ${state.race.link.name.lowercase()}",
                            color = if (state.race.link == LinkState.LINKED) Mint else Muted,
                            fontSize = 11.sp,
                        )
                    }
                },
                actions = {
                    if (state.race.link != LinkState.DISCONNECTED) {
                        OutlinedButton(onClick = leave, modifier = Modifier.padding(end = 8.dp)) { Text("Leave") }
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OriginBar(state, setOrigin, saveOrigin, refresh)
            ModeBar(state, enterLive, chooseRace)
            SessionStrip(state, chooseRace)
            ReplayControls(state, seek)
            state.message?.let { Text(it, color = Signal, style = MaterialTheme.typography.bodySmall) }
            Comparison(state)
            TimingHeader(state.snapshot)
            TimingList(state, toggleDriver, Modifier.weight(1f))
        }
    }
}

@Composable
private fun OriginBar(state: ScreenState, setOrigin: (String) -> Unit, save: () -> Unit, refresh: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedTextField(
            value = state.originInput,
            onValueChange = setOrigin,
            label = { Text("Race Lens origin") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        Button(onClick = save, contentPadding = ButtonDefaults.ContentPadding) { Text("Save") }
        OutlinedButton(onClick = refresh, contentPadding = ButtonDefaults.ContentPadding) { Text("Refresh") }
    }
}

@Composable
private fun ModeBar(state: ScreenState, enterLive: () -> Unit, chooseRace: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Button(
            onClick = { state.sessions.firstOrNull()?.let { chooseRace(it.id) } },
            colors = ButtonDefaults.buttonColors(
                containerColor = if (state.race.race.mode == RaceMode.REPLAY) Signal else Panel
            ),
        ) { Text("REPLAY") }
        Button(
            onClick = enterLive,
            enabled = state.live.available,
            colors = ButtonDefaults.buttonColors(
                containerColor = if (state.race.race.mode == RaceMode.LIVE) Signal else Panel
            ),
        ) { Text(if (state.live.available) "● LIVE" else "LIVE OFF") }
        Text(state.live.detail, color = Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun SessionStrip(state: ScreenState, chooseRace: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("READY REPLAYS", color = Muted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            items(state.sessions, key = { it.id }) { session ->
                val active = state.race.race.mode == RaceMode.REPLAY && state.race.race.raceId == session.id
                OutlinedButton(
                    onClick = { chooseRace(session.id) },
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = if (active) Signal.copy(alpha = .2f) else Color.Transparent),
                ) {
                    Column {
                        Text(session.id.replace('_', ' ').uppercase(), maxLines = 1)
                        Text(session.source.uppercase(), color = Muted, fontSize = 9.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun ReplayControls(state: ScreenState, seek: (Long) -> Unit) {
    val timeline = state.timeline ?: return
    if (state.race.race.mode != RaceMode.REPLAY) return
    val start = timeline.startMs.coerceAtLeast(0)
    val end = timeline.endMs.coerceAtLeast(start + 1)
    var scrub by remember(state.race.race.raceId, state.snapshot?.atMs) {
        mutableFloatStateOf((state.snapshot?.atMs ?: start).coerceIn(start, end).toFloat())
    }
    Card(colors = CardDefaults.cardColors(containerColor = Panel)) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("REPLAY TIME", color = Muted, fontSize = 11.sp)
                Text("${formatTime(scrub.toLong())} / ${formatTime(end)}", fontWeight = FontWeight.Bold)
            }
            Slider(
                value = scrub,
                onValueChange = { scrub = it },
                onValueChangeFinished = { seek(scrub.toLong()) },
                valueRange = start.toFloat()..end.toFloat(),
            )
        }
    }
}

@Composable
private fun Comparison(state: ScreenState) {
    val selected = state.race.race.selectedDriverIds
    if (selected.isEmpty()) return
    val byId = state.snapshot?.drivers?.associateBy { it.id }.orEmpty()
    Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(8.dp)) {
        Column(Modifier.fillMaxWidth().padding(10.dp)) {
            Text("DRIVER COMPARISON", color = Mint, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                selected.forEach { id ->
                    val driver = byId[id]
                    Text(
                        "$id  P${driver?.position ?: "—"}  GAP ${formatGap(driver?.gapSeconds)}  ${driver?.tyre ?: "—"}",
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            Text("Tap a selected timing row to deselect", color = Muted, fontSize = 10.sp)
        }
    }
}

@Composable
private fun TimingHeader(snapshot: RaceSnapshot?) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text("CLASSIFICATION", fontWeight = FontWeight.Black, letterSpacing = 1.sp)
        Text(
            "LAP ${snapshot?.lap ?: "—"}  •  ${snapshot?.status?.uppercase() ?: "WAITING"}",
            color = Muted,
            fontSize = 12.sp,
        )
    }
}

@Composable
private fun TimingList(state: ScreenState, toggleDriver: (String) -> Unit, modifier: Modifier = Modifier) {
    val selected = state.race.race.selectedDriverIds
    val drivers = state.snapshot?.drivers.orEmpty()
    if (drivers.isEmpty()) {
        Box(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Text(if (state.loading) "Loading timing…" else "No timing data", color = Muted)
        }
        return
    }
    LazyColumn(modifier) {
        items(drivers, key = { it.id }) { driver ->
            val isSelected = driver.id in selected
            val canSelect = isSelected || selected.size < 2
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(if (isSelected) Mint.copy(alpha = .14f) else Color.Transparent)
                    .clickable(enabled = canSelect) { toggleDriver(driver.id) }
                    .padding(vertical = 11.dp, horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("${driver.position ?: "—"}", fontWeight = FontWeight.Black, modifier = Modifier.width(32.dp))
                Text(driver.id, fontWeight = FontWeight.Black, modifier = Modifier.width(52.dp))
                TimingCell("GAP", formatGap(driver.gapSeconds), Modifier.width(80.dp))
                TimingCell("INT", formatGap(driver.intervalSeconds), Modifier.width(80.dp))
                TimingCell("TYRE", "${driver.tyre ?: "—"} ${driver.tyreAge?.let { "L$it" } ?: ""}", Modifier.width(80.dp))
                TimingCell("LAPS", driver.laps.toString(), Modifier.width(48.dp))
            }
            HorizontalDivider(color = Color.White.copy(alpha = .07f))
        }
    }
}

@Composable
private fun TimingCell(label: String, value: String, modifier: Modifier) {
    Column(modifier) {
        Text(label, color = Muted, fontSize = 8.sp)
        Text(value, fontSize = 12.sp, maxLines = 1)
    }
}

private fun formatGap(seconds: Double?) = when {
    seconds == null -> "—"
    seconds == 0.0 -> "LEADER"
    else -> "+%.3f".format(seconds)
}

private fun formatTime(ms: Long): String {
    val totalSeconds = ms.coerceAtLeast(0) / 1_000
    return "%d:%02d".format(totalSeconds / 60, totalSeconds % 60)
}
