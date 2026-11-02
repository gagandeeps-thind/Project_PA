package com.osiris.player.ui.training

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bluetooth
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.ble.BleSensors
import com.osiris.player.platform.ble.FoundSensor
import com.osiris.player.platform.location.LocationClient
import com.osiris.player.platform.permission.PermissionStatus
import com.osiris.player.platform.permission.rememberPermission
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.HeroMetric
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.start.PostOrSaveDialog
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.training.Channel
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.start.LivePhase
import com.osiris.shared.presentation.start.LiveSessionViewModel
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.flowOf

private const val MPS_TO_KMH = 3.6

/** Finds the activity by key (the catalog is cached), then records it. */
@Composable
fun LiveSessionScreen(graph: AppGraph, activityKey: String, mode: StartMode, onDone: () -> Unit) {
    val activity by produceState<TrainingActivity?>(null, activityKey) {
        value = graph.data.training.activities().getOrNull()?.firstOrNull { it.key == activityKey }
    }
    val a = activity
    if (a == null) {
        OsirisScaffold("Workout", null, onBack = onDone) { padding ->
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }
    } else {
        Recording(graph, a, mode, onDone)
    }
}

@Composable
private fun Recording(graph: AppGraph, activity: TrainingActivity, mode: StartMode, onDone: () -> Unit) {
    val vm = rememberShared(key = "live-${mode.wire}-${activity.key}") { graph.liveSession(activity, mode) }
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val sensors = remember { BleSensors(context) }
    val connected = remember { mutableStateListOf<FoundSensor>() }
    var showSensors by rememberSaveable { mutableStateOf(false) }
    var askStop by rememberSaveable { mutableStateOf(false) }

    // shortcut: the session records while the screen is on (kept on here); background recording needs a service.
    val view = LocalView.current
    LaunchedEffect(s.phase) { view.keepScreenOn = s.phase == LivePhase.RECORDING }

    Feeds(vm, activity, recording = s.phase == LivePhase.RECORDING, sensors, connected)
    LaunchedEffect(s.finished) { if (s.finished) onDone() }
    BackHandler(enabled = s.phase == LivePhase.RECORDING) { askStop = true }

    val back = { if (s.phase == LivePhase.RECORDING) askStop = true else onDone() }
    OsirisScaffold("${mode.title} · ${activity.name}", vm, onBack = back) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            HeroMetric(Format.duration(s.elapsedS), label = if (s.paused) "Paused" else "Elapsed", caption = Format.distance(s.distanceM))
            LiveTiles(s.live)
            AssistChip(
                onClick = { showSensors = true },
                label = { Text(if (connected.isEmpty()) "Connect a watch or sensor" else "${connected.size} sensor(s) connected") },
                leadingIcon = { Icon(Icons.Outlined.Bluetooth, contentDescription = null) },
            )
            Controls(
                s.phase, s.paused,
                onPauseResume = { if (s.paused) vm.resume() else vm.pause() },
                onStop = { askStop = true },
                onRetry = vm::retry,
            )
        }
    }
    if (askStop) {
        ConfirmDialog(
            title = "Finish ${activity.name}?",
            body = "Your session will be saved.",
            confirm = "Finish",
            onConfirm = {
                askStop = false
                vm.stop()
            },
            dismiss = "Keep going",
            onDismiss = { askStop = false },
        )
    }
    val saved = s.session
    if (s.phase == LivePhase.SAVED && saved != null && !s.finished) {
        PostOrSaveDialog(saved, activity.name, onPost = vm::post, onKeep = vm::keep)
    }
    if (showSensors) {
        SensorsSheet(sensors, connected, onConnect = { if (connected.none { c -> c.address == it.address }) connected += it }) {
            showSensors = false
        }
    }
}

/** GPS fixes (outdoor activities) and each connected sensor's readings, while recording. */
@Composable
private fun Feeds(
    vm: LiveSessionViewModel,
    activity: TrainingActivity,
    recording: Boolean,
    sensors: BleSensors,
    connected: List<FoundSensor>,
) {
    val context = LocalContext.current
    if (activity.gps) {
        val gps = rememberPermission(Manifest.permission.ACCESS_FINE_LOCATION)
        LaunchedEffect(gps, recording) {
            if (gps == PermissionStatus.GRANTED && recording) LocationClient(context).fixes().catch { }.collect(vm::onFix)
        }
    }
    for (sensor in connected) {
        key(sensor.address) {
            LaunchedEffect(recording) {
                if (!recording) return@LaunchedEffect
                vm.deviceConnected(sensor.name)
                sensors.connect(sensor.address).collect { (channel, value) -> vm.onSample(channel, value) }
            }
        }
    }
}

@Composable
private fun Controls(phase: LivePhase, paused: Boolean, onPauseResume: () -> Unit, onStop: () -> Unit, onRetry: () -> Unit) {
    when (phase) {
        LivePhase.RECORDING -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            RaisedButton(onClick = onPauseResume, modifier = Modifier.weight(1f)) { Text(if (paused) "Resume" else "Pause") }
            KeyButton(onClick = onStop, modifier = Modifier.weight(1f)) { Text("Stop") }
        }
        LivePhase.UPLOADING -> Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.padding(end = 12.dp))
            Text("Saving your session…")
        }
        LivePhase.FAILED -> Column {
            Text("Your session is kept on this screen but could not be saved yet.", color = OsirisColors.Error)
            KeyButton(onClick = onRetry, modifier = Modifier.padding(top = 8.dp)) { Text("Retry") }
        }
        LivePhase.SAVED -> Unit
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LiveTiles(live: Map<Channel, Double?>) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), maxItemsInEachRow = 2) {
        for (channel in Channel.entries) {
            val value = live[channel]?.let { if (channel == Channel.SPEED) it * MPS_TO_KMH else it }
            FrostCard(Modifier.weight(1f)) {
                Text(channel.label, style = MaterialTheme.typography.labelMedium, color = OsirisColors.Muted)
                Text(
                    value?.let { Format.fixed(it, if (channel == Channel.SPEED) 1 else 0) } ?: "—",
                    style = MaterialTheme.typography.headlineMedium,
                )
                Text(channel.unit, color = OsirisColors.Faint)
            }
        }
    }
}

/** Scan for Bluetooth fitness sensors and pick the ones to record from. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SensorsSheet(sensors: BleSensors, connected: List<FoundSensor>, onConnect: (FoundSensor) -> Unit, onDismiss: () -> Unit) {
    var allowed by remember { mutableStateOf(sensors.hasPermission()) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { allowed = sensors.hasPermission() }
    LaunchedEffect(Unit) { if (!allowed) ask.launch(sensors.permissions) }
    val found by remember(allowed) { if (allowed) sensors.scan() else flowOf(emptyList()) }
        .collectAsState(initial = emptyList())
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = OsirisColors.Surface) {
        Column(Modifier.padding(horizontal = 20.dp).navigationBarsPadding()) {
            Text("Watches & sensors", style = MaterialTheme.typography.titleLarge)
            Text(
                "Put your watch in heart-rate broadcast mode, or wake your strap, power meter or speed sensor.",
                color = OsirisColors.Muted,
                modifier = Modifier.padding(vertical = 8.dp),
            )
            when {
                !sensors.available -> Text("This phone has no Bluetooth.", color = OsirisColors.Error)
                !allowed -> TextButton(onClick = { ask.launch(sensors.permissions) }) { Text("Allow Bluetooth to find sensors") }
                !sensors.enabled -> Text("Turn Bluetooth on to find sensors.", color = OsirisColors.Warning)
                found.isEmpty() -> Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.padding(end = 12.dp))
                    Text("Looking for sensors…")
                }
                else -> for (f in found) {
                    val on = connected.any { it.address == f.address }
                    ListItem(
                        headlineContent = { Text(f.name) },
                        supportingContent = { Text(f.channels.joinToString { it.label }) },
                        trailingContent = {
                            if (on) {
                                Text("Connected", color = OsirisColors.Success)
                            } else {
                                TextButton(onClick = { onConnect(f) }) { Text("Connect") }
                            }
                        },
                        colors = ListItemDefaults.colors(containerColor = OsirisColors.Surface),
                    )
                }
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp)) { Text("Done") }
        }
    }
}
