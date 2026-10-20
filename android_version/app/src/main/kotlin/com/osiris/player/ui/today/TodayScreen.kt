package com.osiris.player.ui.today

import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.PersonAddAlt
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.WbTwilight
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
    LazyColumn(contentPadding = PaddingValues(16.dp, 12.dp, 16.dp, 32.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Hi ${t.displayName}", style = MaterialTheme.typography.headlineSmall)
            Text("${t.performanceRank} ${t.identity}  •  ${t.xp} XP", color = OsirisColors.Muted)
        }
        if (t.needsLocationConsent) item { ConsentBanner(onAllow) }
        item { QuestCard(t.today, onStart) }
        item { WeekCard(t.week, t.streakWeeks) }
        item {
            Card {
                ListItem(
                    leadingContent = { Icon(Icons.Outlined.WbTwilight, null, tint = OsirisColors.Secondary) },
                    headlineContent = { Text("Tomorrow") },
                    supportingContent = { Text(t.tomorrow.title) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                )
            }
        }
        t.starterChallenge?.let { c -> item { StarterChallengeCard(c, onChallenge) } }
        item { NavGrid(onOpen) }
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

@Composable
private fun ConsentBanner(onAllow: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = OsirisColors.Secondary.copy(alpha = 0.15f))) {
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
private fun QuestCard(quest: Quest, onStart: () -> Unit) {
    Card {
        Column(Modifier.padding(16.dp)) {
            Text(quest.heading, color = OsirisColors.Secondary, fontSize = 12.sp, letterSpacing = 1.2.sp)
            Spacer(Modifier.height(6.dp))
            Text(quest.title, style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(4.dp))
            Text(quest.description, color = OsirisColors.Muted)
            Spacer(Modifier.height(14.dp))
            LinearProgressIndicator(
                progress = { quest.fraction.toFloat() },
                modifier = Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(6.dp)),
                drawStopIndicator = {},
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "${Format.km(quest.progressM)} of ${Format.km(quest.targetM.toDouble())}  •  +${quest.xp} XP",
                color = OsirisColors.Muted,
                fontSize = 13.sp,
            )
            Spacer(Modifier.height(14.dp))
            if (quest.completed) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.CheckCircle, null, tint = OsirisColors.Success)
                    Spacer(Modifier.width(8.dp))
                    Text(if (quest.rewarded) "Done. +${quest.xp} XP earned." else "Done!", Modifier.weight(1f))
                    TextButton(onClick = onStart) { Text("GO AGAIN") }
                }
            } else {
                Button(onClick = onStart, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Filled.PlayArrow, null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (quest.optional) "START (OPTIONAL)" else "START")
                }
            }
        }
    }
}

@Composable
private fun WeekCard(week: WeeklyGoal, streakWeeks: Int) {
    Card {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("THIS WEEK", color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp, modifier = Modifier.weight(1f))
                Icon(
                    Icons.Filled.LocalFireDepartment,
                    null,
                    Modifier.size(18.dp),
                    tint = if (streakWeeks > 0) OsirisColors.Warning else Color.White.copy(alpha = 0.24f),
                )
                Spacer(Modifier.width(4.dp))
                Text(if (streakWeeks == 1) "1 week streak" else "$streakWeeks week streak")
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                repeat(week.activeDaysTarget) { i ->
                    val done = i < week.activeDays
                    Icon(
                        if (done) Icons.Filled.Circle else Icons.Outlined.Circle,
                        null,
                        Modifier.padding(end = 8.dp).size(22.dp),
                        tint = if (done) OsirisColors.Secondary else Color.White.copy(alpha = 0.38f),
                    )
                }
                Spacer(Modifier.weight(1f))
                Text(Format.km(week.distanceM), color = OsirisColors.Muted)
            }
            Spacer(Modifier.height(8.dp))
            Text(
                if (week.completed) {
                    "Weekly goal met. Enjoy your rest days."
                } else {
                    "${week.activeDays} of ${week.activeDaysTarget} active days. Rest days never break your streak."
                },
                color = OsirisColors.Muted,
                fontSize = 13.sp,
            )
        }
    }
}

@Composable
private fun StarterChallengeCard(c: StarterChallenge, onOpen: (Int) -> Unit) {
    val away = c.distanceKm?.let { "  •  about ${Format.fixed(it, 1)} km away" }.orEmpty()
    Card(Modifier.clickable { onOpen(c.id) }) {
        ListItem(
            leadingContent = { Icon(Icons.Outlined.Flag, null, tint = OsirisColors.Primary) },
            headlineContent = { Text(c.title) },
            supportingContent = { Text("${Format.fixed(c.courseDistanceM / 1000, 1)} km course$away  •  free") },
            trailingContent = { Icon(Icons.Filled.ChevronRight, null) },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}

private data class NavItem(val icon: ImageVector, val label: String, val route: String)

private val navItems = listOf(
    NavItem(Icons.Outlined.Groups, "Clubs", Routes.COMMUNITIES),
    NavItem(Icons.Filled.FitnessCenter, "Bodyweight", Routes.EXERCISE),
    NavItem(Icons.Outlined.Route, "My courses", Routes.COURSES),
    NavItem(Icons.Outlined.PersonAddAlt, "Invite", Routes.SETTINGS),
)

/** Three tiles a row; a lazy grid inside the lazy column would need a fixed height. */
@Composable
private fun NavGrid(onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in navItems.chunked(3)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (item in row) {
                    Card(Modifier.weight(1f).height(84.dp).clickable { onOpen(item.route) }) {
                        Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(item.icon, null, tint = OsirisColors.Secondary)
                            Spacer(Modifier.height(6.dp))
                            Text(item.label, fontSize = 13.sp)
                        }
                    }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}
