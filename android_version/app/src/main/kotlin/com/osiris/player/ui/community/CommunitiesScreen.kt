package com.osiris.player.ui.community

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.outlined.VpnKey
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.Community
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.common.Loadable

@Composable
fun CommunitiesScreen(graph: AppGraph, onBack: () -> Unit, onOpen: (String) -> Unit) {
    val vm = rememberShared { graph.communities() }
    val s by vm.state.collectAsStateWithLifecycle()
    var joinWithCode by remember { mutableStateOf(false) }
    // Back from a club page: joining or leaving moves it between the lists.
    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }

    OsirisScaffold(
        "CLUBS & GROUPS",
        vm,
        onBack = onBack,
        actions = { IconButton(onClick = { joinWithCode = true }) { Icon(Icons.Outlined.VpnKey, "Join with a code") } },
    ) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(contentPadding = PaddingValues(16.dp)) {
                section("YOUR GROUPS", s.mine, "Join your running club, gym, or team to compete together.", onOpen) { it }
                item { Spacer(Modifier.size(24.dp)) }
                section("NEAR YOU", s.discover, "No other public groups in your city yet. Set your city in Settings.", onOpen) { list ->
                    list.filterNot { it.isMember }
                }
            }
        }
    }
    if (joinWithCode) {
        JoinWithCodeDialog(
            onJoin = { slug, code ->
                joinWithCode = false
                vm.join(slug, code)
            },
            onDismiss = { joinWithCode = false },
        )
    }
}

private fun LazyListScope.section(
    title: String,
    state: Loadable<List<Community>>,
    empty: String,
    onOpen: (String) -> Unit,
    filter: (List<Community>) -> List<Community>,
) {
    item { Text(title, color = OsirisColors.Muted, fontSize = 12.sp, letterSpacing = 1.2.sp, modifier = Modifier.padding(bottom = 8.dp)) }
    when (state) {
        Loadable.Loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        is Loadable.Failed -> item { Text(state.message, color = OsirisColors.Error) }
        is Loadable.Ready -> {
            val list = filter(state.value)
            if (list.isEmpty()) item { Text(empty) }
            items(list, key = { title + it.slug }) { c -> CommunityTile(c) { onOpen(c.slug) } }
        }
    }
}

@Composable
private fun CommunityTile(c: Community, onClick: () -> Unit) {
    FrostCard(Modifier.padding(vertical = 4.dp), onClick = onClick, contentPadding = 0.dp) {
        ListItem(
            leadingContent = {
                Box(Modifier.size(40.dp).background(brandColor(c.brandColor), CircleShape), contentAlignment = Alignment.Center) {
                    Text(c.name.take(1).uppercase())
                }
            },
            headlineContent = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(c.name, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (c.verified) Icon(Icons.Filled.Verified, "Verified", Modifier.padding(start = 6.dp).size(16.dp), tint = OsirisColors.Secondary)
                }
            },
            supportingContent = { Text("${c.kindLabel}  •  ${c.memberCount} members") },
            trailingContent = { Icon(Icons.Filled.ChevronRight, null) },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        )
    }
}

@Composable
private fun JoinWithCodeDialog(onJoin: (String, String) -> Unit, onDismiss: () -> Unit) {
    var slug by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = OsirisColors.Surface,
        title = { Text("Join a private group") },
        text = {
            Column {
                OutlinedTextField(slug, { slug = it }, label = { Text("Group ID (from the organiser)") }, singleLine = true)
                OutlinedTextField(code, { code = it }, label = { Text("Join code") }, singleLine = true)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("CANCEL") } },
        confirmButton = { Button(onClick = { onJoin(slug.trim(), code.trim()) }) { Text("JOIN") } },
    )
}
