package com.osiris.player.ui.community

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.community.SeasonCard

@Composable
fun RankingsScreen(graph: AppGraph, onBack: () -> Unit, onSettings: () -> Unit) {
    val vm = rememberShared { graph.rankings() }
    val s by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }

    OsirisScaffold("RANKINGS", vm, onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            PrimaryTabRow(selectedTabIndex = tab, containerColor = OsirisColors.Surface) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("THIS WEEK") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("SEASON") })
            }
            if (tab == 0) {
                PullToRefreshBox(isRefreshing = false, onRefresh = vm::refreshLocal) {
                    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
                        item {
                            when (val local = s.local) {
                                Loadable.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                                // Usually "set your city first": the way out is Settings.
                                is Loadable.Failed -> Column {
                                    Text(local.message)
                                    OutlinedButton(onClick = onSettings, modifier = Modifier.padding(top = 12.dp)) { Text("SET MY CITY") }
                                }
                                is Loadable.Ready -> LeaderboardView(local.value)
                            }
                        }
                    }
                }
            } else {
                PullToRefreshBox(isRefreshing = false, onRefresh = vm::refreshSeasons) {
                    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
                        when (val seasons = s.seasons) {
                            Loadable.Loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                            is Loadable.Failed -> item { Text(seasons.message, color = OsirisColors.Error) }
                            is Loadable.Ready -> if (seasons.value.isEmpty()) {
                                item { Text("No season in your city right now. Set your city in Settings to see local seasons.") }
                            } else {
                                items(seasons.value, key = { it.season.slug }) { card -> SeasonCardView(card, onJoin = { vm.joinSeason(card.season.slug) }) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SeasonCardView(card: SeasonCard, onJoin: () -> Unit) {
    val season = card.season
    Card(Modifier.padding(vertical = 6.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(season.name, style = MaterialTheme.typography.titleLarge)
            Text(card.status, color = OsirisColors.Muted)
            season.description?.let { Text(it, Modifier.padding(top = 8.dp)) }
            if (season.entered) {
                Text("You're in. Every active day counts.", color = OsirisColors.Success, modifier = Modifier.padding(top = 12.dp))
            } else {
                Button(onClick = onJoin, modifier = Modifier.padding(top = 12.dp)) { Text("JOIN THE SEASON") }
            }
            val board = card.board ?: return@Column
            if (board.communities.isNotEmpty()) {
                Text("CLUB STANDINGS", color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp, modifier = Modifier.padding(top = 16.dp))
                for (c in board.communities) {
                    ListItem(
                        leadingContent = { Text("#${c.rank}") },
                        headlineContent = { Text(c.name, fontWeight = if (c.isMine) FontWeight.Bold else FontWeight.Normal) },
                        trailingContent = { Text("${c.averagePoints} avg pts") },
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    )
                }
            }
            Column(Modifier.padding(top = 12.dp)) { LeaderboardView(board.players, compact = true) }
        }
    }
}
