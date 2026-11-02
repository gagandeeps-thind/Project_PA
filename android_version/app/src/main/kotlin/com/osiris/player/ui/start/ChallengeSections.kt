package com.osiris.player.ui.start

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.design.RaisedButton
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.GroupChallenge
import com.osiris.shared.domain.model.GroupChallenges
import com.osiris.shared.domain.model.SuggestedChallenge
import com.osiris.shared.presentation.common.Loadable

/** Cards shown on the collapsed group card before the "View all" tile. */
private const val COLLAPSED = 3
private const val SUGGESTED_PER_ROW = 2
private const val METRES_PER_KM = 1000.0
private const val SECONDS_PER_MINUTE = 60.0

/** An amount in this challenge's unit: "12.4 km", "35 min", "40 reps", "2 sessions". */
fun GroupChallenge.amount(value: Double): String = when (metric) {
    "distance_m" -> "${Format.fixed(value / METRES_PER_KM, 1)} km"
    "duration_s" -> "${(value / SECONDS_PER_MINUTE).toInt()} min"
    "reps" -> "${value.toInt()} reps"
    else -> "${value.toInt()} sessions"
}

/** "12.4 km of 20.0 km". */
fun GroupChallenge.progressLabel(): String = "${amount(myProgress)} of ${amount(target)}"

/** One group challenge: title, goal, the player's progress and how many are in. */
@Composable
fun GroupChallengeCard(c: GroupChallenge, onClick: () -> Unit, modifier: Modifier = Modifier) {
    FrostCard(modifier, onClick = onClick) {
        Text(c.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(
            when {
                c.myStatus == "invited" -> "Invited · ${c.members} in"
                !c.active -> "${c.status.replaceFirstChar(Char::titlecase)} · ${c.members} in"
                else -> "${c.members} in · ends ${c.endsAt.toString().take(DATE_CHARS)}"
            },
            style = MaterialTheme.typography.labelMedium,
            color = if (c.myStatus == "invited") OsirisColors.Warning else OsirisColors.Muted,
        )
        Spacer(Modifier.height(10.dp))
        LinearProgressIndicator(
            progress = { c.myFraction.toFloat() },
            modifier = Modifier.fillMaxWidth().height(6.dp),
            color = OsirisColors.Primary,
            trackColor = OsirisColors.Faint.copy(alpha = 0.24f),
            drawStopIndicator = {},
        )
        Text(c.progressLabel(), style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 6.dp))
    }
}

private const val DATE_CHARS = 10

/**
 * Below the Challenge page's start button: Osiris challenges (only if there are any), the group
 * challenges card, then suggested challenges two to a row.
 */
fun LazyListScope.challengeSections(
    groups: Loadable<GroupChallenges>?,
    suggested: List<SuggestedChallenge>,
    expanded: Boolean,
    onToggle: () -> Unit,
    onGroup: (Int) -> Unit,
    onAllGroups: () -> Unit,
    onChallenge: (Int) -> Unit,
) {
    val lists = groups?.valueOrNull
    if (!lists?.official.isNullOrEmpty()) {
        item { SectionHeader("Osiris challenges") }
        item {
            LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                items(lists.official, key = { it.id }) { GroupChallengeCard(it, { onGroup(it.id) }, Modifier.width(240.dp)) }
            }
        }
    }
    item { SectionHeader("Group challenges") }
    item {
        GroupCard(lists?.group.orEmpty(), loading = groups is Loadable.Loading || groups == null, expanded, onToggle, onGroup, onAllGroups)
    }
    if (suggested.isNotEmpty()) {
        item { SectionHeader("Suggested challenges") }
        for (row in suggested.chunked(SUGGESTED_PER_ROW)) {
            item(key = "suggested-${row.first().id}") {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (c in row) SuggestedCard(c, { onChallenge(c.id) }, Modifier.weight(1f))
                    if (row.size < SUGGESTED_PER_ROW) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun GroupCard(
    all: List<GroupChallenge>,
    loading: Boolean,
    expanded: Boolean,
    onToggle: () -> Unit,
    onGroup: (Int) -> Unit,
    onAllGroups: () -> Unit,
) {
    FrostCard(Modifier.fillMaxWidth().padding(horizontal = 16.dp).animateContentSize(), contentPadding = 0.dp) {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onToggle).padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("With your connections", style = MaterialTheme.typography.titleMedium)
                Text(
                    if (loading) "Loading…" else "${all.size} challenge${if (all.size == 1) "" else "s"} · create, join and compete",
                    color = OsirisColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, if (expanded) "Collapse" else "Expand")
        }
        when {
            loading -> Unit
            all.isEmpty() -> Column(Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp)) {
                Text("No group challenges yet. Start one and invite the Osirians you follow.", color = OsirisColors.Muted)
                RaisedButton(onClick = onAllGroups, modifier = Modifier.padding(top = 10.dp)) { Text("Create a group challenge") }
            }
            expanded -> Column(
                Modifier.padding(start = 12.dp, end = 12.dp, bottom = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                for (c in all) GroupChallengeCard(c, { onGroup(c.id) }, Modifier.fillMaxWidth())
                RaisedButton(onClick = onAllGroups, modifier = Modifier.fillMaxWidth()) { Text("Open group challenges") }
            }
            else -> LazyRow(
                contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(all.take(COLLAPSED), key = { it.id }) { GroupChallengeCard(it, { onGroup(it.id) }, Modifier.width(220.dp)) }
                item { ViewAllTile(onAllGroups) }
            }
        }
    }
}

@Composable
private fun ViewAllTile(onClick: () -> Unit) {
    FrostCard(Modifier.width(120.dp).height(118.dp), onClick = onClick) {
        Box(Modifier.fillMaxWidth().height(86.dp), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.AutoMirrored.Outlined.ArrowForward, contentDescription = null)
                Text("View all", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun SuggestedCard(c: SuggestedChallenge, onClick: () -> Unit, modifier: Modifier) {
    FrostCard(modifier.height(132.dp), onClick = onClick) {
        Text(c.title, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(
            c.distanceLabel,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = OsirisColors.Primary,
        )
        Text("Beat ${Format.duration(c.targetSeconds)}", color = OsirisColors.Muted, style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.weight(1f))
        Text(
            if (c.joined) "Joined · ${c.participants} in" else "+${c.winXp} XP · ${c.participants} in",
            color = if (c.joined) OsirisColors.Success else OsirisColors.Secondary,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
