package com.osiris.player.ui.challenge

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Loop
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.Gap
import com.osiris.player.ui.common.ListSpacing
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.challenge.CoursesViewModel

@Composable
fun CoursesScreen(graph: AppGraph, onBack: () -> Unit, onOpenChallenge: (Int) -> Unit, onStartRun: () -> Unit) {
    val vm = rememberShared { graph.courses() }
    val s by vm.state.collectAsStateWithLifecycle()
    var publishing by remember { mutableStateOf<CourseSummary?>(null) }
    LaunchedEffect(s.openChallengeId) {
        s.openChallengeId?.let {
            publishing = null
            vm.opened()
            onOpenChallenge(it)
        }
    }

    OsirisScaffold("MY COURSES", vm, onBack = onBack) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.courses, onRetry = vm::refresh) { courses ->
                if (courses.isEmpty()) {
                    LazyColumn {
                        item {
                            EmptyState(
                                Icons.Outlined.Route,
                                "Your first challenge starts with a run.",
                                "Challenges are raced on a route you ran yourself. Record a verified run of at least " +
                                    "0.7 km, save it as a course when it ends, then publish it here.",
                                actionLabel = "START A RUN",
                                onAction = onStartRun,
                            )
                        }
                    }
                } else {
                    LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = ListSpacing) {
                        items(courses, key = { it.id }) { c ->
                            CourseTile(c, onPublish = { publishing = c }, onView = onOpenChallenge)
                        }
                    }
                }
            }
        }
    }
    publishing?.let { course ->
        PublishDialog(course, vm, busy = s.publishing, onClose = { publishing = null })
    }
}

@Composable
private fun CourseTile(c: CourseSummary, onPublish: () -> Unit, onView: (Int) -> Unit) {
    Card {
        ListItem(
            leadingContent = { Icon(if (c.isLoop) Icons.Filled.Loop else Icons.Outlined.Route, null, tint = OsirisColors.Secondary) },
            headlineContent = { Text(c.name, fontWeight = FontWeight.Bold) },
            supportingContent = { Text("${Format.distance(c.distanceM)} • your time ${Format.duration(c.benchmarkSeconds)}") },
            trailingContent = {
                val live = c.openChallengeId
                when {
                    c.status != "active" -> Text(c.status.uppercase(), color = OsirisColors.Error)
                    live != null -> TextButton(onClick = { onView(live) }) { Text("VIEW LIVE") }
                    else -> Button(onClick = onPublish) { Text("PUBLISH") }
                }
            },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}

private val windows = listOf(24 to "1 day", 72 to "3 days", 168 to "1 week", 336 to "2 weeks")

@Composable
private fun PublishDialog(course: CourseSummary, vm: CoursesViewModel, busy: Boolean, onClose: () -> Unit) {
    var title by rememberSaveable { mutableStateOf("Beat my ${course.name}") }
    var window by rememberSaveable { mutableStateOf(72) }
    var safety by rememberSaveable { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    // One draft per dialog, so its idempotency key survives a retried tap.
    var draft by remember { mutableStateOf<ChallengeDraft?>(null) }

    AlertDialog(
        onDismissRequest = onClose,
        containerColor = OsirisColors.Surface,
        title = { Text("Publish challenge") },
        text = {
            val err = error
            Column {
                Text(
                    "Challengers must beat your time of ${Format.duration(course.benchmarkSeconds)} " +
                        "over ${Format.distance(course.distanceM)}. Terms cannot be edited after publishing.",
                )
                Gap()
                OutlinedTextField(
                    value = title,
                    onValueChange = { if (it.length <= 80) title = it },
                    label = { Text("Title") },
                    singleLine = true,
                    isError = err != null,
                    supportingText = if (err != null) { { Text(err) } } else null,
                    modifier = Modifier.fillMaxWidth(),
                )
                ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                    OutlinedTextField(
                        value = windows.first { it.first == window }.second,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Open for") },
                        modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        for ((hours, label) in windows) {
                            DropdownMenuItem(text = { Text(label) }, onClick = {
                                window = hours
                                expanded = false
                            })
                        }
                    }
                }
                OutlinedTextField(
                    value = safety,
                    onValueChange = { if (it.length <= 200) safety = it },
                    label = { Text("Safety notes (optional)") },
                    placeholder = { Text("e.g. busy crossing at the halfway point") },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
                Gap(8)
                Text("Entry is free. Rewards are XP and badges.", color = OsirisColors.Faint, fontSize = 12.sp)
            }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("CANCEL") } },
        confirmButton = {
            Button(
                enabled = !busy,
                onClick = {
                    val notes = safety.trim().ifEmpty { null }
                    val d = draft?.takeIf { it.title == title.trim() && it.windowHours == window && it.safetyNotes == notes }
                        ?: vm.draft(course, title.trim(), window, notes)
                    draft = d
                    error = d.validate()
                    // The dialog stays open until it is published, so a retry after a failure reuses the key.
                    if (error == null) vm.publish(d)
                },
            ) { Text(if (busy) "PUBLISHING…" else "PUBLISH") }
        },
    )
}
