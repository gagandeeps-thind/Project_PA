package com.osiris.player.ui.social

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Leaderboard
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.TravelExplore
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.ReportKind
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.social.SocialDiscoverState
import com.osiris.shared.presentation.social.SocialDiscoverViewModel

/** Where Discover leads besides posts: the boards and clubs the old Social tab held. */
class DiscoverNav(
    val onBack: () -> Unit,
    val onProfile: (Int) -> Unit,
    val onLeaderboards: () -> Unit,
    val onCommunities: () -> Unit,
)

/** Discover: a "for you" grid of posts from people you don't follow, filtered by activity. */
@Composable
fun SocialDiscoverScreen(graph: AppGraph, nav: DiscoverNav) {
    val vm = rememberShared { graph.socialDiscover() }
    val s by vm.state.collectAsStateWithLifecycle()
    val safety = rememberFeedSafety(graph)
    OsirisScaffold("Discover", vm, onBack = nav.onBack) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AssistChip(
                        onClick = nav.onLeaderboards,
                        label = { Text("Leaderboards") },
                        leadingIcon = { Icon(Icons.Outlined.Leaderboard, null) },
                    )
                    AssistChip(
                        onClick = nav.onCommunities,
                        label = { Text("Clubs & groups") },
                        leadingIcon = { Icon(Icons.Outlined.Groups, null) },
                    )
                }
                ActivityChips(s, vm)
                LoadableContent(s.posts, onRetry = vm::refresh) { posts -> DiscoverGrid(posts, graph, s, vm) }
            }
        }
    }
    s.openPost?.let { post -> OpenPostSheet(post, graph, vm, s, safety, nav.onProfile) }
    PostSheetsHost(vm, safety)
    ModerationHost(safety.vm) {
        vm.open(null)
        vm.refresh()
    }
}

@Composable
private fun ActivityChips(s: SocialDiscoverState, vm: SocialDiscoverViewModel) {
    Row(
        Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(selected = s.activity == null, onClick = { vm.select(null) }, label = { Text("For you") })
        s.chips.forEach { key ->
            FilterChip(
                selected = s.activity == key,
                onClick = { vm.select(key) },
                label = { Text(key.replace('_', ' ').replaceFirstChar { it.uppercase() }) },
            )
        }
    }
}

@Composable
private fun DiscoverGrid(posts: List<FeedPost>, graph: AppGraph, s: SocialDiscoverState, vm: SocialDiscoverViewModel) {
    val grid = rememberLazyGridState()
    val nearEnd by remember {
        derivedStateOf {
            val info = grid.layoutInfo
            info.totalItemsCount > 0 && (info.visibleItemsInfo.lastOrNull()?.index ?: 0) >= info.totalItemsCount - GRID_AHEAD
        }
    }
    LaunchedEffect(nearEnd) { if (nearEnd) vm.loadMore() }
    LazyVerticalGrid(
        columns = GridCells.Fixed(COLUMNS),
        state = grid,
        modifier = Modifier.fillMaxSize(),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        if (posts.isEmpty()) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                EmptyState(
                    Icons.Outlined.TravelExplore,
                    if (s.activity == null) "Nothing new to discover yet" else "No recent posts for this activity",
                    "Posts from the last 30 days by athletes you don't follow show up here.",
                )
            }
        }
        items(posts, key = { it.id }) { post -> PostTile(post, graph.config.apiBaseUrl) { vm.open(post.id) } }
    }
}

@Composable
private fun OpenPostSheet(
    post: FeedPost,
    graph: AppGraph,
    vm: SocialDiscoverViewModel,
    s: SocialDiscoverState,
    safety: FeedSafety,
    onProfile: (Int) -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = { vm.open(null) },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = OsirisColors.Surface,
    ) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp).navigationBarsPadding()) {
            val followed = post.userId in s.followed
            Box(Modifier.fillMaxWidth()) {
                TextButton(onClick = { vm.follow(post.userId) }, enabled = !followed) {
                    Icon(Icons.Outlined.PersonAdd, null)
                    Text(if (followed) "  Following ${post.authorName}" else "  Follow ${post.authorName}")
                }
            }
            SocialPostCard(
                post,
                baseUrl = graph.config.apiBaseUrl,
                now = rememberNow(),
                isMine = false,
                actions = PostCallbacks(
                    onKudos = vm::toggleKudos,
                    onDoubleTap = vm::kudosByDoubleTap,
                    onComments = { vm.openComments(it) },
                    onShare = vm::share,
                    onAuthor = {
                        vm.open(null)
                        onProfile(it)
                    },
                    onDelete = null,
                    onReport = { safety.vm.askReport(ReportKind.POST, it) },
                    onBlock = { safety.vm.askBlock(it.userId, it.authorName) },
                ),
            )
        }
    }
}

private const val COLUMNS = 3
private const val GRID_AHEAD = 6
