package com.osiris.player.ui.challenge

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.HowToReg
import androidx.compose.material.icons.filled.IosShare
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.outlined.PersonAddAlt
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.share.ShareEffect
import com.osiris.player.platform.share.share
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.Gap
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.TermRow
import com.osiris.player.ui.common.localMinute
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.map.CoursePreview
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.ReasonCopy
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.challenge.ChallengeDetail
import com.osiris.shared.presentation.challenge.ChallengeDetailViewModel
import kotlin.math.roundToInt
import kotlinx.coroutines.launch

@Composable
fun ChallengeDetailScreen(graph: AppGraph, id: Int, onBack: () -> Unit, onRun: (Int) -> Unit) {
    val vm = rememberShared { graph.challengeDetail(id) }
    val s by vm.state.collectAsStateWithLifecycle()
    var menu by remember { mutableStateOf(false) }
    var confirmBlock by remember { mutableStateOf(false) }
    ShareEffect(s.share, vm::shared)
    LaunchedEffect(s.closed) { if (s.closed) onBack() }
    // Back from a challenge run: the attempt has a result now.
    var resumedOnce by remember { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }

    OsirisScaffold(
        "CHALLENGE",
        vm,
        onBack = onBack,
        actions = {
            if (s.canInvite) IconButton(onClick = vm::invite) { Icon(Icons.Outlined.PersonAddAlt, "Invite a friend") }
            if (s.canReport) {
                Box {
                    IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, "Report or block") }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        for (reason in s.reportReasons) {
                            DropdownMenuItem(text = { Text(reason.label) }, onClick = {
                                menu = false
                                vm.report(reason)
                            })
                        }
                        DropdownMenuItem(text = { Text("Block this player") }, onClick = {
                            menu = false
                            confirmBlock = true
                        })
                    }
                }
            }
        },
    ) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.detail, onRetry = vm::refresh) { detail ->
                Content(detail, s.joining, vm, onRun)
            }
        }
    }
    if (confirmBlock) {
        ConfirmDialog(
            title = "Block this player?",
            body = "You won't see this player's challenges. You can unblock them in Settings.",
            confirm = "BLOCK",
            onConfirm = {
                confirmBlock = false
                vm.blockCreator()
            },
            dismiss = "CANCEL",
            onDismiss = { confirmBlock = false },
            destructive = true,
        )
    }
}

@Composable
private fun Content(detail: ChallengeDetail, joining: Boolean, vm: ChallengeDetailViewModel, onRun: (Int) -> Unit) {
    val c = detail.challenge
    val now = rememberNow()
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text(c.title, style = MaterialTheme.typography.headlineMedium)
            Text("${c.status.uppercase()} • ${c.closesIn(now)}", color = OsirisColors.Faint)
        }
        val route = detail.course?.route.orEmpty()
        if (route.size >= 2) item { CoursePreview(route) }
        item {
            Card {
                Column(Modifier.padding(16.dp)) {
                    Text("TERMS", fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp)
                    Gap(8)
                    TermRow("Course distance", Format.distance(c.courseDistanceM))
                    TermRow("Time to beat", Format.duration(c.targetSeconds))
                    c.closesAt?.let { TermRow("Closes", "${it.localMinute()} (${c.closesIn(now)})") }
                    TermRow("Entry cost", if (c.entryCrystals == 0) "Free" else "${c.entryCrystals} crystals")
                    TermRow("Reward", "+${c.winXp} XP for a win, +${c.participationXp} XP for a verified finish")
                    TermRow("Attempts so far", "${c.attemptCount}")
                    Gap(8)
                    Text(
                        "Privacy: the map shows only an approximate area. The exact route is shared " +
                            "with players who join. Results are shown without names.",
                        color = OsirisColors.Faint,
                        fontSize = 12.sp,
                    )
                }
            }
        }
        val notes = c.safetyNotes
        if (!notes.isNullOrBlank()) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = OsirisColors.Warning.copy(alpha = 0.12f))) {
                    ListItem(
                        leadingContent = { Icon(Icons.Filled.HealthAndSafety, null, tint = OsirisColors.Warning) },
                        headlineContent = { Text("Safety notes") },
                        supportingContent = { Text(notes) },
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    )
                }
            }
        }
        c.myAttempt?.let { a -> item { AttemptCard(a, vm) } }
        item {
            when {
                c.isMine -> Text(
                    "This is your challenge. You earn XP each time a challenger fails to beat your time.",
                    textAlign = TextAlign.Center,
                    color = OsirisColors.Faint,
                    modifier = Modifier.fillMaxWidth(),
                )
                c.canJoin -> Button(onClick = vm::join, enabled = !joining, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Filled.HowToReg, null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (joining) "JOINING…" else "JOIN CHALLENGE")
                }
                c.canRun -> Button(onClick = { onRun(c.id) }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.AutoMirrored.Filled.DirectionsRun, null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (c.myAttempt?.status == "rejected") "TRY AGAIN" else "RUN THIS COURSE")
                }
            }
        }
    }
}

@Composable
private fun AttemptCard(a: AttemptSummary, vm: ChallengeDetailViewModel) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val color = when {
        a.outcome == "won" -> OsirisColors.Success
        a.status == "rejected" -> OsirisColors.Error
        else -> OsirisColors.Secondary
    }
    Card {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("YOUR ATTEMPT", fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp, modifier = Modifier.weight(1f))
                Text(a.label, color = color, fontWeight = FontWeight.Bold)
            }
            val elapsed = a.elapsedSeconds
            if (elapsed != null && elapsed > 0) {
                Gap(8)
                TermRow("Your time", Format.duration(elapsed))
            }
            a.courseCoverage?.let { TermRow("On course", "${(it * 100).roundToInt()}%") }
            if (a.xpAwarded > 0) TermRow("XP earned", "+${a.xpAwarded}")
            if (a.status == "accepted" && (a.outcome == "won" || a.outcome == "lost")) {
                TextButton(
                    onClick = { scope.launch { vm.shareResult(a.id)?.let { share(context, it) } } },
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Icon(Icons.Filled.IosShare, null)
                    Spacer(Modifier.width(4.dp))
                    Text("SHARE RESULT")
                }
            }
            for (r in a.reasonCodes) Text("• ${ReasonCopy.explain(r)}", color = OsirisColors.Muted, modifier = Modifier.padding(top = 6.dp))
        }
    }
}
