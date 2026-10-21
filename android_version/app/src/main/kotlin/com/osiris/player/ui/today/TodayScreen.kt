package com.osiris.player.ui.today

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.osiris.player.ui.design.HeroMetric
import com.osiris.player.ui.theme.primaryButtonColors
import com.osiris.shared.core.design.FrostMatte
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.PersonAddAlt
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.WbTwilight
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.osiris.player.platform.location.LocationClient
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.navigation.Routes
import com.osiris.player.ui.navigation.open
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.Quest
import com.osiris.shared.domain.model.StarterChallenge
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.WeeklyGoal
import com.osiris.shared.presentation.AppGraph
import kotlinx.coroutines.flow.firstOrNull

@Composable
fun TodayScreen(graph: AppGraph, nav: NavHostController) {
    val vm = rememberShared { graph.today() }
    val state by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val location = remember { LocationClient(context) }

    // One position for the nearby starter challenge; without permission the suggestion is skipped.
    LaunchedEffect(Unit) {
        val fix = if (location.hasPermission()) runCatching { location.fixes().firstOrNull() }.getOrNull() else null
        if (fix != null) vm.onPosition(fix.position) else vm.onNoPosition()
    }

    OsirisScaffold(
        "OSIRIS",
        vm,
        actions = { IconButton(onClick = { nav.open(Routes.SETTINGS) }) { Icon(Icons.Outlined.Settings, "Settings") } },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = false,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            LoadableContent(state, onRetry = vm::refresh) { t ->
                Today(
                    t,
                    onAllow = vm::grantLocationConsent,
                    onStart = {
                        vm.onStartQuest()
                        nav.open(Routes.run())
                    },
                    onChallenge = { nav.open(Routes.challenge(it)) },
                    onOpen = nav::open,
                )
            }
        }
    }
    // Back from a run or another screen: the quest progress may have moved. The first resume is the
    // initial load, which the view model already started.
    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }
}

@Composable
private fun Today(t: TodayData, onAllow: () -> Unit, onStart: () -> Unit, onChallenge: (Int) -> Unit, onOpen: (String) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            Text("Hi ${t.displayName}", style = MaterialTheme.typography.titleMedium, color = OsirisColors.Muted)
            Text(
                "${t.performanceRank} ${t.identity}  ·  ${t.xp} XP",
                style = MaterialTheme.typography.bodySmall,
                color = OsirisColors.Faint,
            )
        }
        if (t.needsLocationConsent) item { ConsentBanner(onAllow) }
        item { QuestCard(t.today, onStart) }
        item { WeekStrip(t.week, t.streakWeeks) }
        item { Shortcuts(t.tomorrow.title, onOpen) }
        t.starterChallenge?.let { c -> item { StarterChallengeCard(c, onChallenge) } }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.HealthAndSafety, null, Modifier.size(18.dp), tint = OsirisColors.Faint)
                Spacer(Modifier.width(8.dp))
                Text(t.safetyNote, color = OsirisColors.Faint, fontSize = 12.sp)
            }
            Text(t.tagline, color = OsirisColors.Faint, fontSize = 12.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        }
    }
}

/** The screen's focal point: today's quest distance, at hero size; everything else in it recedes. */
@Composable
private fun QuestCard(quest: Quest, onStart: () -> Unit) {
    FrostCard(radius = FrostMatte.Radius.LARGE, contentPadding = 22.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                quest.heading.uppercase(),
                style = MaterialTheme.typography.labelMedium,
                color = OsirisColors.Muted,
                modifier = Modifier.weight(1f),
            )
            Text("+${quest.xp} XP", style = MaterialTheme.typography.labelMedium, color = OsirisColors.Muted)
        }
        Spacer(Modifier.height(12.dp))
        HeroMetric(Format.fixed(quest.progressM / 1000, 2), unit = "/ ${Format.km(quest.targetM.toDouble())}")
        Spacer(Modifier.height(6.dp))
        Text("${quest.title}. ${quest.description}", style = MaterialTheme.typography.bodyMedium, color = OsirisColors.Muted)
        Spacer(Modifier.height(14.dp))
        LinearProgressIndicator(
            progress = { quest.fraction.toFloat() },
            modifier = Modifier.fillMaxWidth().height(12.dp).clip(RoundedCornerShape(6.dp)),
            trackColor = OsirisColors.Background,
            gapSize = 0.dp,
            drawStopIndicator = {},
        )
        Spacer(Modifier.height(16.dp))
        if (quest.completed) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.CheckCircle, null, tint = OsirisColors.Success)
                Spacer(Modifier.width(8.dp))
                Text(if (quest.rewarded) "Done. +${quest.xp} XP earned." else "Done!", Modifier.weight(1f))
                TextButton(onClick = onStart) { Text("GO AGAIN") }
            }
        } else {
            Button(onClick = onStart, colors = primaryButtonColors(), modifier = Modifier.fillMaxWidth().height(56.dp)) {
                Icon(Icons.Filled.PlayArrow, null)
                Spacer(Modifier.width(6.dp))
                Text(if (quest.optional) "START (OPTIONAL)" else "START")
            }
        }
    }
}

/** The week, kept quiet: day keys, a count and the streak. No card, so it never competes with the quest. */
@Composable
private fun WeekStrip(week: WeeklyGoal, streakWeeks: Int) {
    val summary = if (week.completed) {
        "Weekly goal met. Rest days never break your streak."
    } else {
        "${week.activeDays} of ${week.activeDaysTarget} active days this week, ${Format.km(week.distanceM)}"
    }
    Row(
        Modifier.padding(horizontal = 4.dp).semantics(mergeDescendants = true) { contentDescription = summary },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(week.activeDaysTarget) { i ->
            val shape = RoundedCornerShape(9.dp)
            val day = Modifier.padding(end = 8.dp).size(26.dp)
            if (i < week.activeDays) {
                Spacer(day.background(OsirisColors.Muted, shape))
            } else {
                Spacer(day.border(2.dp, OsirisColors.Faint.copy(alpha = 0.5f), shape))
            }
        }
        Text(
            "${week.activeDays} of ${week.activeDaysTarget} days",
            style = MaterialTheme.typography.titleSmall,
            color = OsirisColors.Muted,
            modifier = Modifier.weight(1f),
        )
        if (streakWeeks > 0) {
            Text("$streakWeeks WK STREAK", style = MaterialTheme.typography.labelMedium, color = OsirisColors.Secondary)
        }
    }
}

/** Asymmetric block: tomorrow's quest tall on the left, two shortcuts stacked right, two pills below. */
@Composable
private fun Shortcuts(tomorrow: String, onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.height(188.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FrostCard(Modifier.weight(1.15f).fillMaxHeight(), radius = FrostMatte.Radius.LARGE) {
                Text("TOMORROW", style = MaterialTheme.typography.labelMedium, color = OsirisColors.Muted)
                Spacer(Modifier.weight(1f))
                Icon(Icons.Outlined.WbTwilight, null, tint = OsirisColors.Faint)
                Spacer(Modifier.height(8.dp))
                Text(tomorrow, style = MaterialTheme.typography.headlineSmall)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Shortcut(Icons.Outlined.Groups, "Clubs", Modifier.weight(1f)) { onOpen(Routes.COMMUNITIES) }
                Shortcut(Icons.Filled.FitnessCenter, "Bodyweight", Modifier.weight(1f)) { onOpen(Routes.EXERCISE) }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Pill(Icons.Outlined.Route, "My courses") { onOpen(Routes.COURSES) }
            Pill(Icons.Outlined.PersonAddAlt, "Invite a friend") { onOpen(Routes.SETTINGS) }
        }
    }
}

@Composable
private fun Shortcut(icon: ImageVector, label: String, modifier: Modifier, onClick: () -> Unit) {
    FrostCard(modifier.fillMaxWidth(), onClick = onClick, contentPadding = 16.dp) {
        Spacer(Modifier.weight(1f))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Icon(icon, null, Modifier.size(20.dp), tint = OsirisColors.Faint)
        }
    }
}

/** Secondary destinations as outlined pills: an interactive border, no fill to compete with the cards. */
@Composable
private fun Pill(icon: ImageVector, label: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        border = BorderStroke(1.5.dp, OsirisColors.Faint.copy(alpha = 0.6f)),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = OsirisColors.Muted),
        modifier = Modifier.height(44.dp),
    ) {
        Icon(icon, null, Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
private fun ConsentBanner(onAllow: () -> Unit) {
    FrostCard(contentPadding = 0.dp, fill = OsirisColors.Secondary.copy(alpha = 0.15f)) {
        ListItem(
            leadingContent = { Icon(Icons.Outlined.LocationOn, null) },
            headlineContent = { Text("Allow location during runs") },
            supportingContent = { Text("Needed to verify your distance. Your route is never shown to others.") },
            trailingContent = { TextButton(onClick = onAllow) { Text("ALLOW") } },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}

@Composable
private fun StarterChallengeCard(c: StarterChallenge, onOpen: (Int) -> Unit) {
    val away = c.distanceKm?.let { "  •  about ${Format.fixed(it, 1)} km away" }.orEmpty()
    FrostCard(onClick = { onOpen(c.id) }, contentPadding = 0.dp) {
        ListItem(
            leadingContent = { Icon(Icons.Outlined.Flag, null, tint = OsirisColors.Primary) },
            headlineContent = { Text(c.title) },
            supportingContent = { Text("${Format.fixed(c.courseDistanceM / 1000, 1)} km course$away  •  free") },
            trailingContent = { Icon(Icons.Filled.ChevronRight, null) },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}
