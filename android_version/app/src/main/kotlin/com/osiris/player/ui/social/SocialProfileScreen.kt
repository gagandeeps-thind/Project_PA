package com.osiris.player.ui.social

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyGridScope
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.KeyButton
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.social.SocialProfileViewModel

/** A player's profile: counts, this week's training, follow and message, and a grid of their posts. */
@Composable
fun SocialProfileScreen(graph: AppGraph, userId: Int, onBack: () -> Unit, onMessage: (Int) -> Unit, onCompose: () -> Unit) {
    val vm = rememberShared(key = "profile-$userId") { graph.socialProfile(userId) }
    val s by vm.state.collectAsStateWithLifecycle()
    var openPostId by rememberSaveable { mutableStateOf<Int?>(null) }
    OsirisScaffold(s.profile.valueOrNull?.user?.handle?.let { "@$it" } ?: "Profile", vm, onBack = onBack) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.profile, onRetry = vm::refresh) { p ->
                LazyVerticalGrid(
                    columns = GridCells.Fixed(COLUMNS),
                    modifier = Modifier.fillMaxSize(),
                    horizontalArrangement = Arrangement.spacedBy(2.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    header(p, s.followBusy, vm, onMessage, onCompose)
                    items(p.posts, key = { it.id }) { post -> PostTile(post, graph.config.apiBaseUrl) { openPostId = post.id } }
                }
            }
        }
    }
    val open = s.profile.valueOrNull?.posts?.firstOrNull { it.id == openPostId }
    if (open != null) {
        ModalBottomSheet(
            onDismissRequest = { openPostId = null },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = OsirisColors.Surface,
        ) {
            Column(Modifier.padding(12.dp)) {
                SocialPostCard(
                    open,
                    baseUrl = graph.config.apiBaseUrl,
                    now = rememberNow(),
                    isMine = s.profile.valueOrNull?.isMe == true,
                    actions = PostCallbacks(
                        onKudos = vm::toggleKudos,
                        onDoubleTap = vm::kudosByDoubleTap,
                        onComments = { vm.openComments(it) },
                        onShare = vm::share,
                        onAuthor = { openPostId = null },
                        onDelete = {
                            openPostId = null
                            vm.delete(it)
                        },
                    ),
                )
            }
        }
    }
    PostSheetsHost(vm)
}

private fun LazyGridScope.header(
    p: SocialProfile,
    busy: Boolean,
    vm: SocialProfileViewModel,
    onMessage: (Int) -> Unit,
    onCompose: () -> Unit,
) {
    item(span = { GridItemSpan(maxLineSpan) }) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(p.user.initials, size = 80.dp, ring = p.weekSessions > 0)
                Spacer(Modifier.width(16.dp))
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.SpaceEvenly) {
                    Count("${p.postsCount}", "Posts")
                    Count("${p.followersCount}", "Followers")
                    Count("${p.followingCount}", "Following")
                }
            }
            Text(p.user.displayName, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 10.dp))
            Text("${p.user.rank} · ${p.title}", color = OsirisColors.Secondary, fontSize = 12.sp)
            p.bio?.takeIf { it.isNotBlank() }?.let { Text(it, modifier = Modifier.padding(top = 4.dp)) }
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                Count("${p.weekSessions}", "Sessions this week")
                Count("${p.weekMinutes}", "Minutes this week")
                Count("${p.streakDays}d", "Streak")
            }
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                when {
                    p.isMe -> KeyButton(onClick = onCompose, modifier = Modifier.weight(1f)) { Text("New post") }
                    p.user.following -> OutlinedButton(onClick = vm::toggleFollow, enabled = !busy, modifier = Modifier.weight(1f)) {
                        Text("Following")
                    }
                    else -> KeyButton(onClick = vm::toggleFollow, enabled = !busy, modifier = Modifier.weight(1f)) {
                        Text(if (p.user.followsMe) "Follow back" else "Follow")
                    }
                }
                if (p.canMessage) {
                    OutlinedButton(onClick = { onMessage(p.user.userId) }, modifier = Modifier.weight(1f)) { Text("Message") }
                }
            }
        }
    }
    if (p.posts.isEmpty()) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            EmptyState(Icons.Outlined.PhotoCamera, if (p.isMe) "Share your first workout" else "No posts yet")
        }
    }
}

@Composable
private fun Count(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.ExtraBold)
        Text(label, fontSize = 11.sp, color = OsirisColors.Faint)
    }
}

private const val COLUMNS = 3
