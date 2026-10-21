package com.osiris.player.ui.challenge

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.TravelExplore
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.location.CurrentPosition
import com.osiris.player.ui.common.Chip
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.ListSpacing
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.Notice
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.presentation.AppGraph
import kotlin.time.Instant

@Composable
fun ChallengeBoardScreen(graph: AppGraph, onBack: (() -> Unit)?, onOpen: (Int) -> Unit) {
    val vm = rememberShared { graph.challengeBoard() }
    val s by vm.state.collectAsStateWithLifecycle()
    var unavailable by remember { mutableStateOf<String?>(null) }
    var menu by remember { mutableStateOf(false) }
    CurrentPosition(onPosition = vm::onPosition, onUnavailable = { unavailable = it.userMessage })
    // Back from a challenge: a join or attempt changes its chip.
    LifecycleResumeEffect(Unit) {
        vm.refresh()
        onPauseOrDispose {}
    }

    OsirisScaffold(
        "CHALLENGES",
        vm,
        onBack = onBack,
        actions = {
            IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.TravelExplore, "Search radius") }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                for (r in s.radii) {
                    DropdownMenuItem(text = { Text("Within ${r.toInt()} km") }, onClick = {
                        menu = false
                        vm.setRadius(r)
                    })
                }
            }
        },
    ) { padding ->
        val message = unavailable
        if (message != null) {
            Notice(message, Modifier.padding(padding))
            return@OsirisScaffold
        }
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.challenges, onRetry = vm::refresh) { list ->
                val now = rememberNow()
                if (list.isEmpty()) {
                    LazyColumn {
                        item {
                            EmptyState(
                                Icons.Outlined.EmojiEvents,
                                "No open challenges within ${s.radiusKm.toInt()} km.",
                                "Record a run, register it as a course, and publish the first one.",
                            )
                        }
                    }
                } else {
                    LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = ListSpacing) {
                        items(list, key = { it.id }) { c -> ChallengeTile(c, now) { onOpen(c.id) } }
                    }
                }
            }
        }
    }
}

@Composable
fun ChallengeTile(c: ChallengeSummary, now: Instant, onClick: () -> Unit) {
    val away = c.distanceKm?.let { "~${Format.fixed(it, 1)} km away • " }.orEmpty()
    Card(Modifier.clickable(onClick = onClick)) {
        ListItem(
            leadingContent = { Icon(Icons.Filled.EmojiEvents, null, Modifier.size(32.dp), tint = OsirisColors.Warning) },
            headlineContent = { Text(c.title, fontWeight = FontWeight.Bold) },
            supportingContent = {
                Text(
                    "${Format.distance(c.courseDistanceM)} • beat ${Format.duration(c.targetSeconds)}\n" +
                        "$away${c.closesIn(now)} • ${c.attemptCount} attempts",
                )
            },
            trailingContent = {
                Column(horizontalAlignment = Alignment.End) {
                    Text("+${c.winXp} XP", color = OsirisColors.Primary, fontWeight = FontWeight.Bold)
                    when {
                        c.isMine -> Chip("Yours", OsirisColors.Secondary)
                        c.myAttempt != null -> Chip(c.myAttempt!!.label, OsirisColors.Success)
                    }
                }
            },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}
