package com.osiris.player.ui.arise

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.AriseDomain
import com.osiris.shared.domain.model.AriseDomains

private val CARD_WIDTH = 260.dp
private val PHOTO_HEIGHT = 120.dp

/** Attack mode's panel: domains the player is likely to win, then the hard ones. */
fun LazyListScope.domainCarousels(domains: AriseDomains?, baseUrl: String, onAttack: (AriseDomain) -> Unit) {
    if (domains == null) {
        item(key = "domains-loading") { Text("Finding domains near you…", color = OsirisColors.Faint, modifier = Modifier.padding(16.dp)) }
        return
    }
    carousel("Suggested", "No domains you are likely to win nearby yet.", domains.suggested, baseUrl, onAttack)
    carousel("High difficulty", "No hard domains nearby.", domains.hard, baseUrl, onAttack)
}

private fun LazyListScope.carousel(
    title: String,
    empty: String,
    list: List<AriseDomain>,
    baseUrl: String,
    onAttack: (AriseDomain) -> Unit,
) {
    item(key = "title-$title") { SectionHeader(title) }
    item(key = "row-$title") {
        if (list.isEmpty()) {
            Text(empty, color = OsirisColors.Faint, modifier = Modifier.padding(horizontal = 16.dp))
        } else {
            LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                items(list, key = { it.id }) { DomainCard(it, baseUrl, onAttack) }
            }
        }
    }
}

@Composable
private fun DomainCard(domain: AriseDomain, baseUrl: String, onAttack: (AriseDomain) -> Unit) {
    FrostCard(Modifier.width(CARD_WIDTH), contentPadding = 12.dp) {
        val photo = domain.photoUrl?.let { rememberRemoteImage(baseUrl.trimEnd('/') + it) }
        Box(
            Modifier.fillMaxWidth().height(PHOTO_HEIGHT).clip(RoundedCornerShape(12.dp)).background(OsirisColors.Surface),
            contentAlignment = Alignment.Center,
        ) {
            if (photo != null) {
                Image(photo, "Photo of ${domain.ownerName}'s domain", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxWidth())
            } else {
                Text("No photo yet", color = OsirisColors.Faint)
            }
        }
        Text(
            "${domain.ownerName}'s domain",
            style = MaterialTheme.typography.titleMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(top = 8.dp),
        )
        Text("Beat ${Format.duration(domain.durationS)} over ${Format.km(domain.distanceM)}", color = OsirisColors.Muted)
        Text(
            domain.workout?.let { "Then ${it.totalReps} reps in ${it.sets.size} sets" } ?: "No workout to repeat",
            color = OsirisColors.Faint,
        )
        Button(onClick = { onAttack(domain) }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("Attack") }
    }
}
