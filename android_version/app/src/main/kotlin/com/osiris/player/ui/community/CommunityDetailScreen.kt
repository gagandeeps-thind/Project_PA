package com.osiris.player.ui.community

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CardGiftcard
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.VpnKey
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.TeamGoal
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.community.CommunityDetail
import com.osiris.shared.presentation.community.CommunityDetailViewModel

@Composable
fun CommunityDetailScreen(graph: AppGraph, slug: String, onBack: () -> Unit, onOpenChallenge: (Int) -> Unit) {
    val vm = rememberShared { graph.community(slug) }
    val s by vm.state.collectAsStateWithLifecycle()
    var menu by remember { mutableStateOf(false) }
    LaunchedEffect(s.left) { if (s.left) onBack() }
    val name = s.detail.valueOrNull?.community?.name

    OsirisScaffold(
        name ?: "GROUP",
        vm,
        onBack = onBack,
        actions = {
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, "More") }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("Report this group") }, onClick = {
                        menu = false
                        vm.report()
                    })
                }
            }
        },
    ) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.detail, onRetry = vm::refresh) { detail -> Content(detail, vm, onOpenChallenge) }
        }
    }
}

@Composable
private fun Content(detail: CommunityDetail, vm: CommunityDetailViewModel, onOpenChallenge: (Int) -> Unit) {
    val c = detail.community
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // The club's brand colour, as the Flutter app tints its header.
        item { Box(Modifier.fillMaxWidth().height(6.dp).background(brandColor(c.brandColor), RoundedCornerShape(3.dp))) }
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(c.kindLabel, color = OsirisColors.Muted)
                if (c.verified) {
                    Icon(Icons.Filled.Verified, null, Modifier.padding(start = 8.dp).size(16.dp), tint = OsirisColors.Secondary)
                    Text(" Verified", color = OsirisColors.Secondary)
                }
            }
            c.description?.let { Text(it, Modifier.padding(top = 8.dp)) }
        }
        c.perkText?.let { perk ->
            item {
                Card {
                    ListItem(
                        leadingContent = { Icon(Icons.Filled.CardGiftcard, null, tint = OsirisColors.Warning) },
                        headlineContent = { Text("Member perk") },
                        supportingContent = { Text(perk) },
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    )
                }
            }
        }
        c.joinCode?.let { code ->
            item {
                Card {
                    ListItem(
                        leadingContent = { Icon(Icons.Outlined.VpnKey, null) },
                        headlineContent = { Text("Join code: $code") },
                        supportingContent = { Text("Group ID: ${c.slug}. Share both with your members.") },
                        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    )
                }
            }
        }
        if (c.myRole != "owner") {
            item {
                Button(onClick = { if (c.isMember) vm.leave() else vm.join() }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
                    Text(if (c.isMember) "LEAVE GROUP" else "JOIN GROUP")
                }
            }
        }
        c.teamGoal?.let { goal -> item { TeamGoalCard(goal) } }
        item {
            Text("GROUP CHALLENGES", color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp, modifier = Modifier.padding(top = 8.dp))
            if (detail.challenges.isEmpty()) Text("No featured challenges right now.", Modifier.padding(vertical = 8.dp))
        }
        items(detail.challenges, key = { it.id }) { ch ->
            Card(Modifier.clickable { onOpenChallenge(ch.id) }) {
                ListItem(
                    leadingContent = { Icon(Icons.Outlined.Flag, null) },
                    headlineContent = { Text(ch.title) },
                    supportingContent = { Text("${Format.distance(ch.courseDistanceM)}  •  target ${Format.duration(ch.targetSeconds)}  •  free") },
                    trailingContent = { Icon(Icons.Filled.ChevronRight, null) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                )
            }
        }
        item {
            val board = detail.leaderboard
            when {
                board != null -> Column(Modifier.padding(top = 8.dp)) { LeaderboardView(board) }
                !c.isMember -> Text("Join to see the weekly leaderboard.", color = OsirisColors.Muted, modifier = Modifier.padding(top = 8.dp))
            }
        }
    }
}

@Composable
private fun TeamGoalCard(goal: TeamGoal) {
    Card(Modifier.padding(top = 8.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text("TEAM GOAL THIS WEEK", color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp)
            Text(
                "${Format.fixed(goal.progressKm, 1)} of ${Format.fixed(goal.goalKm, 0)} km together",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(vertical = 8.dp),
            )
            LinearProgressIndicator(
                progress = { goal.fraction.toFloat() },
                modifier = Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(6.dp)),
                drawStopIndicator = {},
            )
            Text(
                if (goal.completed) {
                    "Goal reached. Nice work, team."
                } else {
                    "${goal.activeMembers} members active so far. Every verified km counts (up to 10 km a day each)."
                },
                color = OsirisColors.Muted,
                fontSize = 13.sp,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}
