package com.osiris.player.ui.profile

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.health.HealthAvailability
import com.osiris.player.platform.health.HealthConnectImporter
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.start.TelemetryCharts
import com.osiris.player.ui.start.summaryLine
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.model.WeeklyProgress
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import kotlinx.coroutines.launch

private const val BAR_GAP = 0.3f
private const val SECONDS_PER_MINUTE = 60
private const val DATE_CHARS = 10
private const val MONTH_DAY = 5
private const val HEALTH_CONNECT_STORE =
    "market://details?id=com.google.android.apps.healthdata&url=healthconnect%3A%2F%2Fonboarding"

/**
 * Profile → Progress: every saved session, posted or not. Weekly time over eight weeks, recent
 * sessions filtered by activity, each one's charts, and the Health Connect import.
 */
@Composable
fun ProgressSection(graph: AppGraph) {
    val vm = rememberShared { graph.progress() }
    val s by vm.state.collectAsStateWithLifecycle()
    val names by produceState(emptyMap<String, String>()) {
        value = graph.data.training.activities().getOrNull()?.associate { it.key to it.name }.orEmpty()
    }
    // Saveable: this screen leaves composition while another is open, and must still refresh on return.
    var resumed by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumed) vm.refresh() else resumed = true
        onPauseOrDispose { }
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Progress", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
        FrostCard(Modifier.fillMaxWidth()) {
            Text("Time trained per week", color = OsirisColors.Muted)
            WeeklyBars(s.weeks)
        }
        val used = s.weeks.flatMap { it.byActivity.keys }.toSortedSet()
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip(selected = s.activity == null, onClick = { vm.filter(null) }, label = { Text("All") })
            for (key in used) {
                FilterChip(selected = s.activity == key, onClick = { vm.filter(key) }, label = { Text(names[key] ?: key) })
            }
        }
        when (val list = s.sessions) {
            is Loadable.Ready -> if (list.value.isEmpty()) {
                Text("No sessions yet. Start one from the Start tab.", color = OsirisColors.Muted)
            } else {
                for (session in list.value) SessionRow(session, names[session.activityKey] ?: session.activityKey) { vm.open(session.id) }
            }
            is Loadable.Failed -> Text(list.message, color = OsirisColors.Error)
            Loadable.Loading -> Unit
        }
        HealthImport(graph, onImported = vm::refresh)
    }
    s.detail?.let { SessionSheet(it, names[it.activityKey] ?: it.activityKey, onDismiss = vm::close) }
}

@Composable
private fun SessionRow(s: TrainingSession, name: String, onClick: () -> Unit) {
    FrostCard(Modifier.fillMaxWidth(), onClick = onClick) {
        Row {
            Text(name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Text(s.startedAt.toString().take(DATE_CHARS), color = OsirisColors.Faint)
        }
        Text(summaryLine(s), color = OsirisColors.Muted)
        val tags = listOfNotNull(
            "Challenge".takeIf { s.mode == "challenge" },
            "PR".takeIf { s.isPr },
            "Posted".takeIf { s.posted },
            "Health Connect".takeIf { s.source == "health_connect" },
        )
        if (tags.isNotEmpty()) Text(tags.joinToString(" · "), color = OsirisColors.Secondary, style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun WeeklyBars(weeks: List<WeeklyProgress>) {
    val minutes = weeks.map { it.durationS / SECONDS_PER_MINUTE }
    val top = (minutes.maxOrNull() ?: 0.0).coerceAtLeast(1.0)
    val color = OsirisColors.Primary
    val track = OsirisColors.Faint.copy(alpha = 0.2f)
    Canvas(
        Modifier.fillMaxWidth().height(120.dp).padding(top = 8.dp).semantics {
            contentDescription = "Minutes per week, oldest first: " + minutes.joinToString { it.toInt().toString() }
        },
    ) {
        if (weeks.isEmpty()) return@Canvas
        val slot = size.width / weeks.size
        val bar = slot * (1 - BAR_GAP)
        minutes.forEachIndexed { i, m ->
            val x = i * slot + (slot - bar) / 2
            drawRoundRect(track, Offset(x, 0f), Size(bar, size.height), CornerRadius(6f))
            val h = (m / top * size.height).toFloat()
            drawRoundRect(color, Offset(x, size.height - h), Size(bar, h), CornerRadius(6f))
        }
    }
    Row(Modifier.fillMaxWidth()) {
        for (w in weeks) {
            Text(
                w.weekStart.takeLast(MONTH_DAY),
                style = MaterialTheme.typography.labelSmall,
                color = OsirisColors.Faint,
                modifier = Modifier.weight(1f),
            )
        }
    }
    val total = minutes.lastOrNull()?.toInt() ?: 0
    Text("This week: $total min", style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 4.dp))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SessionSheet(s: TrainingSession, name: String, onDismiss: () -> Unit) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp).navigationBarsPadding()) {
            Text(name, style = MaterialTheme.typography.headlineSmall)
            Text("${s.startedAt.toString().take(DATE_CHARS)} · ${summaryLine(s)}", color = OsirisColors.Muted)
            if (s.elevationGainM > 0) Text("Climbed ${s.elevationGainM.toInt()} m", color = OsirisColors.Muted)
            TelemetryCharts(s, Modifier.padding(top = 12.dp))
        }
    }
}

/** Import from Health Connect: ask for read access once, then upload the last 30 days. */
@Composable
private fun HealthImport(graph: AppGraph, onImported: () -> Unit) {
    val context = LocalContext.current
    val importer = remember { HealthConnectImporter(context, graph.data.training) }
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    fun run() {
        busy = true
        status = "Importing…"
        scope.launch {
            status = when (val r = importer.import()) {
                is Outcome.Success -> if (r.value == 0) "No new workouts to import." else "Imported ${r.value} workout(s)."
                is Outcome.Failure -> r.error.userMessage
            }
            busy = false
            onImported()
        }
    }
    val ask = rememberLauncherForActivityResult(importer.permissionContract) { granted ->
        if (granted.containsAll(importer.permissions)) run() else status = "Health Connect access was not allowed."
    }
    FrostCard(Modifier.fillMaxWidth()) {
        Text("Health Connect", style = MaterialTheme.typography.titleMedium)
        Text("Bring in workouts from Samsung Health, Fitbit, Google Fit and your watch apps.", color = OsirisColors.Muted)
        when (importer.availability()) {
            HealthAvailability.READY -> RaisedButton(
                onClick = { scope.launch { if (importer.granted()) run() else ask.launch(importer.permissions) } },
                enabled = !busy,
                modifier = Modifier.padding(top = 10.dp),
            ) { Text("Import last 30 days") }
            HealthAvailability.NOT_INSTALLED -> RaisedButton(
                onClick = {
                    try {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(HEALTH_CONNECT_STORE)))
                    } catch (_: ActivityNotFoundException) {
                        status = "Install Health Connect from the Play Store."
                    }
                },
                modifier = Modifier.padding(top = 10.dp),
            ) { Text("Get Health Connect") }
            HealthAvailability.UNSUPPORTED -> Text("Health Connect is not available on this phone.", color = OsirisColors.Faint)
        }
        status?.let { Text(it, color = OsirisColors.Secondary, modifier = Modifier.padding(top = 8.dp)) }
    }
}
