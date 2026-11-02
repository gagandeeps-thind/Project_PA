package com.osiris.player.ui.training

import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.start.GroupChallengeCard
import com.osiris.player.ui.start.amount
import com.osiris.player.ui.start.progressLabel
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.Connection
import com.osiris.shared.domain.model.GroupChallenge
import com.osiris.shared.domain.model.NewGroupChallenge
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.presentation.AppGraph

private enum class GroupTab(val label: String) { MINE("Mine"), INVITED("Invited"), CONNECTIONS("From connections") }

private const val METRES_PER_KM = 1000
private const val SECONDS_PER_MINUTE = 60
private const val MAX_DAYS = 90
private const val TITLE_MIN = 3
private const val TITLE_MAX = 80
private const val DATE_CHARS = 10

/** Group challenges: mine, invites and ones from connections, and a form to start one. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GroupChallengesScreen(graph: AppGraph, onBack: () -> Unit, onOpen: (Int) -> Unit) {
    val vm = rememberShared { graph.groupChallenges() }
    val s by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf(GroupTab.MINE) }
    var creating by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(s.created) {
        s.created?.let {
            creating = false
            vm.createdOpened()
            onOpen(it.id)
        }
    }
    OsirisScaffold("Group challenges", vm, onBack = onBack, actions = {
        IconButton(onClick = { creating = true }) { Icon(Icons.Outlined.Add, contentDescription = "Create a group challenge") }
    }) { padding ->
        LoadableContent(s.lists, onRetry = vm::load, modifier = Modifier.padding(padding)) { lists ->
            val shown = when (tab) {
                GroupTab.MINE -> lists.mine
                GroupTab.INVITED -> lists.invited
                GroupTab.CONNECTIONS -> lists.connections
            }
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(16.dp)) {
                item {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (t in GroupTab.entries) FilterChip(selected = t == tab, onClick = { tab = t }, label = { Text(t.label) })
                    }
                }
                if (shown.isEmpty()) {
                    item {
                        EmptyState(
                            icon = Icons.Outlined.Groups,
                            title = when (tab) {
                                GroupTab.MINE -> "You are not in a group challenge yet"
                                GroupTab.INVITED -> "No invites right now"
                                GroupTab.CONNECTIONS -> "Nothing from your connections yet"
                            },
                            body = "Start one with the + button and invite the Osirians you follow.",
                        )
                    }
                }
                items(shown, key = { it.id }) {
                    GroupChallengeCard(it, { onOpen(it.id) }, Modifier.fillMaxWidth().padding(top = 10.dp))
                }
            }
        }
    }
    if (creating) {
        CreateGroupChallengeSheet(s.activities, s.connections, busy = s.busy, onCreate = vm::create) { creating = false }
    }
}

/** Title, activity, goal, length and who to invite. Distance is typed in km and time in minutes. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun CreateGroupChallengeSheet(
    activities: List<TrainingActivity>,
    connections: List<Connection>,
    busy: Boolean,
    onCreate: (NewGroupChallenge) -> Unit,
    onDismiss: () -> Unit,
) {
    var title by rememberSaveable { mutableStateOf("") }
    var activityKey by rememberSaveable { mutableStateOf("run") }
    var metric by rememberSaveable { mutableStateOf("distance_m") }
    var target by rememberSaveable { mutableStateOf("") }
    var days by rememberSaveable { mutableStateOf("7") }
    var invited by rememberSaveable { mutableStateOf(setOf<Int>()) }
    val activity = activities.firstOrNull { it.key == activityKey }
    val metrics = listOfNotNull(activity?.metric?.takeIf { it != "duration_s" }, "duration_s", "sessions")
    if (metric !in metrics) metric = metrics.first()
    val draft = draftOf(title, activityKey, metric, target, days, invited)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("New group challenge", style = MaterialTheme.typography.titleLarge)
            OutlinedTextField(
                title, { if (it.length <= TITLE_MAX) title = it },
                label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
            ChipRow("Activity", activities, { it.name }, { it.key == activityKey }) { activityKey = it.key }
            ChipRow("Goal", metrics, ::metricName, { it == metric }) { metric = it }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    target, { target = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text("Target (${metricUnit(metric)})") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    days, { days = it.filter(Char::isDigit).take(2) }, label = { Text("Days") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.width(96.dp),
                )
            }
            ChipRow("Invite connections", connections, { it.displayName }, { it.userId in invited }) { c ->
                invited = if (c.userId in invited) invited - c.userId else invited + c.userId
            }
            if (connections.isEmpty()) {
                Text("Follow other Osirians to invite them. Your followers can still join.", color = OsirisColors.Faint)
            }
            KeyButton(
                onClick = { draft?.let(onCreate) },
                enabled = draft != null && !busy,
                modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
            ) { Text(if (busy) "Creating…" else "Create") }
        }
    }
}

/** A labelled row of choice chips. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun <T> ChipRow(label: String, items: List<T>, name: (T) -> String, selected: (T) -> Boolean, onClick: (T) -> Unit) {
    Text(label, color = OsirisColors.Muted)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for (item in items) FilterChip(selected = selected(item), onClick = { onClick(item) }, label = { Text(name(item)) })
    }
}

/** The form as a challenge to create, or null while it is incomplete. Distance is typed in km, time in minutes. */
private fun draftOf(
    title: String,
    activityKey: String,
    metric: String,
    target: String,
    days: String,
    invited: Set<Int>,
): NewGroupChallenge? {
    val amount = target.toDoubleOrNull()?.takeIf { it > 0 }
    val dayCount = days.toIntOrNull()?.takeIf { it in 1..MAX_DAYS }
    if (amount == null || dayCount == null || title.trim().length < TITLE_MIN) return null
    val value = when (metric) {
        "distance_m" -> amount * METRES_PER_KM
        "duration_s" -> amount * SECONDS_PER_MINUTE
        else -> amount
    }
    return NewGroupChallenge(title.trim(), activityKey, metric, value, dayCount, invited.toList())
}

private fun metricName(m: String) = when (m) {
    "distance_m" -> "Distance"
    "duration_s" -> "Time"
    "reps" -> "Reps"
    else -> "Sessions"
}

private fun metricUnit(m: String) = when (m) {
    "distance_m" -> "km"
    "duration_s" -> "min"
    "reps" -> "reps"
    else -> "sessions"
}

/** One group challenge: goal, window, my progress, the leaderboard, and Join or Leave. */
@Composable
fun GroupChallengeDetailScreen(graph: AppGraph, id: Int, onBack: () -> Unit) {
    val vm = rememberShared(key = "group-$id") { graph.groupChallenge(id) }
    val s by vm.state.collectAsStateWithLifecycle()
    var cancelling by rememberSaveable { mutableStateOf(false) }
    if (cancelling) {
        ConfirmDialog(
            title = "Cancel this challenge?",
            body = "It ends for everyone in it. Sessions already done stay in each player's history.",
            confirm = "Cancel challenge",
            onConfirm = {
                cancelling = false
                vm.cancel()
            },
            dismiss = "Keep it",
            onDismiss = { cancelling = false },
            destructive = true,
        )
    }
    OsirisScaffold(s.challenge.valueOrNull?.title ?: "Group challenge", vm, onBack = onBack) { padding ->
        LoadableContent(s.challenge, onRetry = vm::load, modifier = Modifier.padding(padding)) { c ->
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(16.dp)) {
                item { Header(c) }
                item {
                    Spacer(Modifier.height(12.dp))
                    when {
                        !c.active -> Text("This challenge has ${c.status}.", color = OsirisColors.Muted)
                        c.myStatus == "invited" -> KeyButton(onClick = vm::join, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                            Text("Accept invite")
                        }
                        !c.joined -> KeyButton(onClick = vm::join, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("Join") }
                        c.createdByMe -> RaisedButton(
                            onClick = { cancelling = true },
                            enabled = !s.busy,
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("Cancel challenge") }
                        else -> RaisedButton(onClick = vm::leave, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("Leave") }
                    }
                    Text(
                        "Sessions you start from the Challenge page count here.",
                        color = OsirisColors.Faint,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
                item {
                    Text(
                        "Leaderboard",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 20.dp, bottom = 8.dp),
                    )
                }
                itemsIndexed(c.leaderboard, key = { _, m -> m.userId }) { i, m ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("${i + 1}", fontWeight = FontWeight.Bold, modifier = Modifier.width(28.dp))
                        Box(
                            Modifier.size(32.dp).background(OsirisColors.Primary.copy(alpha = 0.24f), CircleShape),
                            contentAlignment = Alignment.Center,
                        ) { Text(m.displayName.take(1).uppercase()) }
                        Text(m.displayName, modifier = Modifier.weight(1f).padding(start = 10.dp))
                        Text(c.amount(m.progress), fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun Header(c: GroupChallenge) {
    FrostCard(Modifier.fillMaxWidth()) {
        Text(if (c.isOfficial) "Osiris challenge" else "Group challenge", color = OsirisColors.Secondary)
        Text(c.title, style = MaterialTheme.typography.headlineSmall)
        Text(
            "Goal ${c.amount(c.target)} · ${c.members} in · until ${c.endsAt.toString().take(DATE_CHARS)}",
            color = OsirisColors.Muted,
        )
        Spacer(Modifier.height(12.dp))
        LinearProgressIndicator(
            progress = { c.myFraction.toFloat() },
            modifier = Modifier.fillMaxWidth().height(8.dp),
            color = OsirisColors.Primary,
            trackColor = OsirisColors.Faint.copy(alpha = 0.24f),
            drawStopIndicator = {},
        )
        Text("You: ${c.progressLabel()}", modifier = Modifier.padding(top = 6.dp))
    }
}
