package com.osiris.player.ui.discover

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.discover.DiscoverCard
import com.osiris.shared.presentation.discover.DiscoverState

/**
 * Happening now, upcoming, community and just-finished challenges, shown in the Arise pull-up panel.
 * The buttons create a challenge from one of the player's courses and open challenges near the player.
 */
fun LazyListScope.discoverSections(state: DiscoverState, onOpen: (Int) -> Unit, onRetry: (HubSection) -> Unit) {
    for (section in HubSection.entries) {
        item(key = section.wire) { Section(section, state.sections.getValue(section), onOpen, onRetry = { onRetry(section) }) }
    }
}

@Composable
fun DiscoverActions(onCreate: () -> Unit, onNearby: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextButton(onClick = onCreate) {
            Icon(Icons.Outlined.Add, null)
            Text("Create challenge")
        }
        TextButton(onClick = onNearby) {
            Icon(Icons.Outlined.Map, null)
            Text("Challenges near me")
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

