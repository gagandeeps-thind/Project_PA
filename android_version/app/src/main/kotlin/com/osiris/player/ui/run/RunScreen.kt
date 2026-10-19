package com.osiris.player.ui.run

import android.Manifest
import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.location.LocationClient
import com.osiris.player.platform.location.LocationUnavailable
import com.osiris.player.platform.location.RunTrackingService
import com.osiris.player.platform.permission.PermissionStatus
import com.osiris.player.platform.permission.rememberPermission
import com.osiris.player.platform.share.share
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.InfoDialog
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.TextInputDialog
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.map.OsmMap
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.core.error.AppError
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.run.RunDialog
import com.osiris.shared.presentation.run.RunState
import com.osiris.shared.presentation.run.RunViewModel
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch

@Composable
fun RunScreen(graph: AppGraph, challengeId: Int?, onBack: () -> Unit, onOpenChallenge: (Int) -> Unit) {
    val vm = rememberShared { graph.run(challengeId) }
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val location = remember { LocationClient(context) }

    val notifications = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) arrayOf(Manifest.permission.POST_NOTIFICATIONS) else emptyArray()
    val permission = rememberPermission(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION, *notifications)

    // GPS runs while this screen is open, recording or not; the service keeps it alive with the screen off.
    LaunchedEffect(permission) {
        when (permission) {
            PermissionStatus.UNKNOWN -> Unit
            PermissionStatus.REFUSED -> vm.onLocationUnavailable(LocationClient.permissionError())
            PermissionStatus.GRANTED -> location.fixes()
                .catch { e -> vm.onLocationUnavailable((e as? LocationUnavailable)?.error ?: AppError.Unexpected(e)) }
                .collect(vm::onLocation)
        }
    }
    LaunchedEffect(s.recording) {
        if (s.recording) RunTrackingService.start(context) else RunTrackingService.stop(context)
    }
    DisposableEffect(Unit) { onDispose { RunTrackingService.stop(context) } }

    OsirisScaffold(
        s.title,
        vm,
        onBack = onBack,
        actions = {
            if (s.recording) {
                IconButton(onClick = vm::requestDiscard, enabled = !s.busy) { Icon(Icons.Filled.DeleteOutline, "Discard run") }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (s.locating && s.position == null) {
                CircularProgressIndicator(Modifier.align(Alignment.Center))
            } else {
                OsmMap(
                    position = s.position,
                    course = s.course,
                    trace = s.trace,
                    nearby = if (s.challengeId == null) s.nearby else emptyList(),
                    follow = s.recording,
                    onChallenge = if (s.recording) null else onOpenChallenge,
                    modifier = Modifier.fillMaxSize(),
                )
            }
            Column(Modifier.fillMaxWidth().padding(12.dp)) {
                if (s.challengeId != null && !s.recording) {
                    Card(colors = CardDefaults.cardColors(containerColor = OsirisColors.Surface)) {
                        Text(
                            "Go to the green start zone, then tap START. Finish inside the red zone. " +
                                "Run safely: obey traffic rules and stop if you feel unwell.",
                            Modifier.padding(12.dp),
                        )
                    }
                }
                if (s.recording) Metrics(s)
            }
            RunButton(s, vm::toggle, Modifier.align(Alignment.BottomEnd).padding(16.dp))
        }
    }
    Dialogs(s.dialog, vm)
}

@Composable
private fun Metrics(s: RunState) {
    val run = s.run ?: return
    Card(colors = CardDefaults.cardColors(containerColor = OsirisColors.Surface.copy(alpha = 0.92f))) {
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceAround) {
            Metric("TIME", s.elapsed)
            Metric("DISTANCE", s.distance)
            Metric("PACE /km", s.pace?.removeSuffix(" /km") ?: "--")
            Metric(if (s.offline) "OFFLINE" else "SYNCED", "${run.uploaded}/${run.nextSequence}", if (s.offline) OsirisColors.Warning else null)
        }
    }
}

@Composable
private fun Metric(label: String, value: String, color: Color? = null) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = color ?: Color.White)
        Text(label, fontSize = 11.sp, color = color ?: OsirisColors.Faint)
    }
}

@Composable
private fun RunButton(s: RunState, onClick: () -> Unit, modifier: Modifier) {
    // A run cannot start before the first GPS fix.
    val waiting = s.busy || (!s.recording && s.position == null)
    ExtendedFloatingActionButton(
        onClick = { if (!waiting) onClick() },
        containerColor = when {
            s.recording -> OsirisColors.Error
            s.position == null -> OsirisColors.Surface
            else -> OsirisColors.Primary
        },
        contentColor = Color.White,
        icon = {
            if (waiting) {
                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
            } else {
                Icon(if (s.recording) Icons.Filled.Stop else Icons.Filled.PlayArrow, null)
            }
        },
        text = { Text(if (s.recording) "FINISH RUN" else if (s.position == null) "LOCATING…" else "START RUN") },
        modifier = modifier,
    )
}

@Composable
private fun Dialogs(dialog: RunDialog?, vm: RunViewModel) {
    when (dialog) {
        null -> Unit
        RunDialog.StaleRun -> ConfirmDialog(
            title = "Unfinished run found",
            body = "A run you started a while ago was never finished. Submit what was recorded, or discard it and start fresh?",
            confirm = "SUBMIT IT",
            onConfirm = vm::finish,
            dismiss = "DISCARD",
            onDismiss = vm::discard,
        )
        RunDialog.LowLight -> ConfirmDialog(
            title = "It's dark out",
            body = "Run on lit routes you know, wear something bright or reflective, " +
                "and tell someone your route and when you expect to be back.",
            confirm = "START ANYWAY",
            onConfirm = { vm.start(confirmedLowLight = true) },
            dismiss = "NOT NOW",
            onDismiss = vm::dismissDialog,
        )
        RunDialog.ConfirmDiscard -> ConfirmDialog(
            title = "Discard this run?",
            body = "The recorded route is deleted from this phone and the run will not count.",
            confirm = "DISCARD",
            onConfirm = vm::discard,
            dismiss = "KEEP RUNNING",
            onDismiss = vm::dismissDialog,
            destructive = true,
        )
        is RunDialog.Celebrate -> Celebrate(dialog, vm)
        is RunDialog.OfferCourse -> TextInputDialog(
            title = "Make it a challenge?",
            body = "Register this route as a course others can challenge? The first and last 150 m are trimmed off for your privacy.",
            label = "Course name",
            confirm = "REGISTER",
            onConfirm = { name -> vm.registerCourse(dialog.runId, name) },
            dismiss = "NOT NOW",
            onDismiss = vm::dismissDialog,
        )
        is RunDialog.Info -> InfoDialog(dialog.title, dialog.body, vm::dismissDialog)
    }
}

@Composable
private fun Celebrate(d: RunDialog.Celebrate, vm: RunViewModel) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = vm::dismissDialog,
        containerColor = OsirisColors.Surface,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.EmojiEvents, null, tint = OsirisColors.Gold)
                Spacer(Modifier.size(8.dp))
                Text(d.title)
            }
        },
        text = {
            Column {
                Text(d.summary)
                Spacer(Modifier.height(8.dp))
                Text(d.xp, color = OsirisColors.Secondary)
                d.week?.let { Text(it, Modifier.padding(top = 8.dp)) }
                d.tomorrow?.let { Text(it, color = OsirisColors.Muted) }
            }
        },
        dismissButton = {
            TextButton(onClick = { scope.launch { vm.shareRun(d.runId)?.let { share(context, it) } } }) {
                Icon(Icons.Filled.Share, null)
                Spacer(Modifier.size(4.dp))
                Text("SHARE")
            }
        },
        confirmButton = { Button(onClick = vm::dismissDialog) { Text("NICE") } },
    )
}
