package com.osiris.player.ui.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.profile.ProfileSummary

/** Header with rank, XP gauge through the current rank, metrics grid and badges. */
@Composable
fun ProfileScreen(graph: AppGraph, actions: @Composable RowScope.() -> Unit = {}) {
    val vm = rememberShared { graph.profile() }
    val state by vm.state.collectAsStateWithLifecycle()
    OsirisScaffold("PROFILE", vm, actions = actions) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(state, onRetry = vm::refresh) { p ->
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Header(p)
                    Gauge(p)
                    Metrics(p)
                    Badges(p)
                }
            }
        }
    }
}

@Composable
private fun Header(p: ProfileSummary) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(64.dp).background(OsirisColors.Primary.copy(alpha = 0.24f), CircleShape), contentAlignment = Alignment.Center) {
            Text(p.name.take(1).uppercase(), style = MaterialTheme.typography.headlineMedium)
        }
        Spacer(Modifier.width(16.dp))
        Column {
            Text(p.name, style = MaterialTheme.typography.titleLarge)
            Text("${p.rank}  •  ${p.goal}", color = OsirisColors.Muted, letterSpacing = 1.sp)
        }
    }
}

@Composable
private fun Gauge(p: ProfileSummary) {
    FrostCard(Modifier.fillMaxWidth()) {
        Row {
            Text(p.xp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Text(p.toNext, color = OsirisColors.Faint)
        }
        Spacer(Modifier.height(10.dp))
        LinearProgressIndicator(
            progress = { p.gauge.toFloat() },
            modifier = Modifier.fillMaxWidth().height(8.dp),
            color = OsirisColors.Warning,
            trackColor = OsirisColors.Faint.copy(alpha = 0.24f),
            drawStopIndicator = {},
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Metrics(p: ProfileSummary) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp), maxItemsInEachRow = 2) {
        for (m in p.metrics) {
            FrostCard(Modifier.weight(1f)) {
                Text(m.value, style = MaterialTheme.typography.titleLarge)
                Text(m.label.uppercase(), color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.sp)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Badges(p: ProfileSummary) {
    val badges = p.progression.badges
    if (badges.isEmpty()) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for (b in badges) {
            AssistChip(
                onClick = {},
                label = { Text(b.label, fontSize = 12.sp) },
                leadingIcon = { Icon(Icons.Filled.Verified, null, Modifier.size(16.dp), tint = OsirisColors.Secondary) },
            )
        }
    }
}
