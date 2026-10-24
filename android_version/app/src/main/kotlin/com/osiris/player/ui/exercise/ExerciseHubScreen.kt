package com.osiris.player.ui.exercise

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.filled.DirectionsWalk
import androidx.compose.material.icons.filled.AccessibilityNew
import androidx.compose.material.icons.filled.AirlineSeatFlatAngled
import androidx.compose.material.icons.filled.AirlineSeatLegroomExtra
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.HorizontalRule
import androidx.compose.material.icons.filled.SportsGymnastics
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.exercise.RecentSetRow

fun exerciseIcon(key: String): ImageVector = when (key) {
    "pushup" -> Icons.Filled.FitnessCenter
    "squat" -> Icons.Filled.AirlineSeatLegroomExtra
    "lunge" -> Icons.AutoMirrored.Filled.DirectionsWalk
    "situp" -> Icons.Filled.AirlineSeatFlatAngled
    "jumping_jack" -> Icons.Filled.AccessibilityNew
    "high_knees" -> Icons.AutoMirrored.Filled.DirectionsRun
    "plank" -> Icons.Filled.HorizontalRule
    else -> Icons.Filled.SportsGymnastics
}

@Composable
fun ExerciseHubScreen(graph: AppGraph, onBack: () -> Unit, onOpen: (String) -> Unit) {
    val vm = rememberShared { graph.exerciseHub() }
    val s by vm.state.collectAsStateWithLifecycle()
    var bannerConsent by remember { mutableStateOf(false) }
    LaunchedEffect(s.open) {
        s.open?.let {
            vm.opened()
            onOpen(it.key)
        }
    }
    // Back from a set: show it in the recent list and sync it.
    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.returned() else resumedOnce = true
        onPauseOrDispose {}
    }

    OsirisScaffold("Bodyweight", vm, onBack = onBack) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.exercises, onRetry = vm::refresh) { tiles ->
                LazyColumn(contentPadding = PaddingValues(16.dp, 12.dp, 16.dp, 32.dp)) {
                    item {
                        FrostCard(contentPadding = 0.dp) {
                            ListItem(
                                leadingContent = { Icon(Icons.Outlined.Lock, null, tint = OsirisColors.Secondary) },
                                headlineContent = { Text("Your camera stays on your phone") },
                                supportingContent = {
                                    Text("Reps are counted on this device. No video or photos are saved or uploaded; only your rep count and timings are.")
                                },
                                trailingContent = if (s.consented) null else { { TextButton(onClick = { bannerConsent = true }) { Text("ALLOW") } } },
                                colors = clear(),
                            )
                        }
                    }
                    items(tiles, key = { it.spec.key }) { t ->
                        FrostCard(Modifier.padding(top = 8.dp), onClick = { vm.select(t.spec) }, contentPadding = 0.dp) {
                            ListItem(
                                leadingContent = { Icon(exerciseIcon(t.spec.key), null, tint = OsirisColors.Secondary) },
                                headlineContent = { Text(t.spec.name) },
                                supportingContent = { Text(if (t.spec.camera == "front") "Face the camera" else "Side-on to the camera") },
                                trailingContent = {
                                    if (t.best == null) Icon(Icons.Filled.ChevronRight, null) else Text("Best ${t.best}", color = OsirisColors.Secondary)
                                },
                                colors = clear(),
                            )
                        }
                    }
                    if (s.recent.isNotEmpty()) {
                        item { Text("Recent sets", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 24.dp, bottom = 8.dp)) }
                        items(s.recent, key = { it.id }) { RecentSet(it) }
                    }
                }
            }
        }
    }
    if (s.askConsentFor != null) ExerciseConsentSheet(vm::consentAnswered)
    if (bannerConsent) {
        ExerciseConsentSheet { allow ->
            bannerConsent = false
            if (allow) vm.grantConsent()
        }
    }
}

@Composable
private fun RecentSet(r: RecentSetRow) {
    val color = when (r.tone) {
        RecentSetRow.Tone.NEUTRAL -> OsirisColors.Faint
        RecentSetRow.Tone.GOOD -> OsirisColors.Success
        RecentSetRow.Tone.WARN -> OsirisColors.Warning
        RecentSetRow.Tone.BAD -> OsirisColors.Error
    }
    ListItem(
        leadingContent = { Icon(exerciseIcon(r.exerciseKey), null, Modifier.size(20.dp)) },
        headlineContent = { Text(r.title) },
        supportingContent = { Text(r.time) },
        trailingContent = { Text(r.status, color = color) },
        colors = clear(),
    )
}

@Composable
private fun clear() = ListItemDefaults.colors(containerColor = Color.Transparent)
