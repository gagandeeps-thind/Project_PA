package com.osiris.player.ui.discover

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.discover.DiscoverCard

/**
 * Happening now, upcoming, community and just-finished challenges. The button creates a challenge
 * from one of the player's courses; the map icon opens challenges near the player.
 */
@Composable
fun DiscoverScreen(graph: AppGraph, onOpen: (Int) -> Unit, onCreate: () -> Unit, onNearby: () -> Unit) {
    val vm = rememberShared { graph.discover() }
    val state by vm.state.collectAsStateWithLifecycle()
    OsirisScaffold("DISCOVER", vm, actions = {
        IconButton(onClick = onNearby) { Icon(Icons.Outlined.Map, "Challenges near me") }
    }) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh) {
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 96.dp)) {
                    for (section in HubSection.entries) {
                        item(key = section.wire) {
                            Section(section, state.sections.getValue(section), onOpen, onRetry = { vm.load(section) })
                        }
                    }
                }
            }
            ExtendedFloatingActionButton(
                onClick = onCreate,
                icon = { Icon(Icons.Outlined.Add, null) },
                text = { Text("CREATE CHALLENGE") },
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
            )
        }
    }
}

@Composable
private fun Section(section: HubSection, cards: Loadable<List<DiscoverCard>>, onOpen: (Int) -> Unit, onRetry: () -> Unit) {
    SectionHeader(section.title)
    when (cards) {
        Loadable.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(horizontal = 16.dp))
        is Loadable.Failed -> TextButton(onClick = onRetry, modifier = Modifier.padding(horizontal = 8.dp)) {
            Text("${cards.message} Tap to retry.", color = OsirisColors.Error)
        }
        is Loadable.Ready -> if (cards.value.isEmpty()) {
            Text(section.empty, color = OsirisColors.Faint, modifier = Modifier.padding(horizontal = 16.dp))
        } else {
            LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                items(cards.value, key = { it.challengeId }) { card ->
                    FrostCard(Modifier.width(260.dp).height(112.dp), onClick = { onOpen(card.challengeId) }) {
                        Text(card.headline, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(card.detail, color = OsirisColors.Muted, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

