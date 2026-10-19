package com.osiris.player.ui.progress

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MilitaryTech
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.progress.ProgressSummary

@Composable
fun ProgressScreen(graph: AppGraph, onBack: () -> Unit) {
    val vm = rememberShared { graph.progress() }
    val state by vm.state.collectAsStateWithLifecycle()
    OsirisScaffold("PROGRESS", vm, onBack = onBack) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(state, onRetry = vm::refresh) { p ->
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) { ProgressionCard(p) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProgressionCard(p: ProgressSummary) {
    Card {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.MilitaryTech, null, tint = OsirisColors.Warning)
                Spacer(Modifier.width(8.dp))
                Text(p.rank, fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp, fontSize = 16.sp, modifier = Modifier.weight(1f))
                Text(p.toNext, color = OsirisColors.Faint)
            }
            if (p.progression.nextRankXp != null) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { p.fraction.toFloat() },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = OsirisColors.Warning,
                    trackColor = Color.White.copy(alpha = 0.12f),
                    drawStopIndicator = {},
                )
            }
            Spacer(Modifier.height(12.dp))
            Text(p.totals, color = OsirisColors.Muted, fontSize = 13.sp)
            if (p.progression.badges.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (b in p.progression.badges) {
                        AssistChip(
                            onClick = {},
                            label = { Text(b.label, fontSize = 12.sp) },
                            leadingIcon = { Icon(Icons.Filled.Verified, null, Modifier.size(16.dp), tint = OsirisColors.Secondary) },
                        )
                    }
                }
            }
        }
    }
}
