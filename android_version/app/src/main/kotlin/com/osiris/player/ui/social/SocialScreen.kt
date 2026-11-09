package com.osiris.player.ui.social

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.AddBox
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.TravelExplore
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.platform.share.ShareEffect
import com.osiris.player.ui.common.ConfirmDialog
import com.osiris.player.ui.common.EmptyState
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.MessageEffect
import com.osiris.player.ui.common.rememberNow
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.HudPill
import com.osiris.player.ui.design.LocalTabBarInset
import com.osiris.player.ui.today.CommentsSheet
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.ReportKind
import com.osiris.shared.presentation.AppGraph
import com.osiris.shared.presentation.social.PostListViewModel

/** Where the Social tab's top bar and posts lead. */
class SocialNav(
    val onCompose: () -> Unit,
    val onDiscover: () -> Unit,
    val onSearch: () -> Unit,
    val onMessages: () -> Unit,
    val onProfile: (Int) -> Unit,
)

/**
 * The Social tab, after Instagram's home: posts by people you follow. The top bar runs, left to
 * right, New post (+), Discover, Search and Messages.
 */
@Composable
fun SocialScreen(graph: AppGraph, nav: SocialNav) {
    val vm = rememberShared { graph.socialFeed() }
    val s by vm.state.collectAsStateWithLifecycle()
    val safety = rememberFeedSafety(graph)
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(vm, snackbar)
    // Back from the composer, a profile or a chat: new posts, follows and read messages show up.
    var resumedOnce by rememberSaveable { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        if (resumedOnce) vm.refresh() else resumedOnce = true
        onPauseOrDispose {}
    }
    val barInset = LocalTabBarInset.current
    Scaffold(
        topBar = { SocialTopBar(s.unreadMessages, nav) },
        snackbarHost = { SnackbarHost(snackbar, Modifier.padding(bottom = barInset)) { HudPill(it.visuals.message) } },
        contentWindowInsets = WindowInsets(0.dp),
        containerColor = Color.Transparent,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) { padding ->
        PullToRefreshBox(isRefreshing = s.refreshing, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.posts, onRetry = vm::refresh) { posts ->
                val listState = rememberLazyListState()
                val nearEnd by remember {
                    derivedStateOf {
                        val info = listState.layoutInfo
                        val last = info.visibleItemsInfo.lastOrNull()?.index ?: 0
                        info.totalItemsCount > 0 && last >= info.totalItemsCount - LOAD_AHEAD
                    }
                }
                LaunchedEffect(nearEnd, s.canLoadMore) { if (nearEnd && s.canLoadMore) vm.loadMore() }
                // A new post at the top (yours, just shared, or a friend's) brings the feed back up to it.
                val topId = posts.firstOrNull()?.id
                var seenTopId by rememberSaveable { mutableStateOf(topId) }
                LaunchedEffect(topId) {
                    if (topId != null && topId != seenTopId) listState.animateScrollToItem(0)
                    seenTopId = topId
                }
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 12.dp, top = 4.dp, end = 12.dp, bottom = 4.dp + barInset),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    item { ActiveTodayRow(s.activeToday, onCompose = nav.onCompose, onOpen = nav.onProfile) }
                    if (posts.isEmpty()) {
                        item {
                            EmptyState(
                                Icons.Outlined.Groups,
                                "Your feed is empty",
                                "Follow athletes you train with and their verified workouts show up here.",
                                actionLabel = "Discover athletes",
                                onAction = nav.onDiscover,
                            )
                        }
                    }
                    postItems(posts, graph, vm, safety, nav.onProfile)
                    if (s.loadingMore) {
                        item {
                            Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                        }
                    }
                }
            }
        }
    }
    PostSheetsHost(vm, safety)
    ModerationHost(safety.vm, onBlocked = vm::refresh)
}

@Composable
private fun SocialTopBar(unread: Int, nav: SocialNav) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 4.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = nav.onCompose) { Icon(Icons.Outlined.AddBox, contentDescription = "New post") }
        IconButton(onClick = nav.onDiscover) { Icon(Icons.Outlined.TravelExplore, contentDescription = "Discover") }
        IconButton(onClick = nav.onSearch) { Icon(Icons.Outlined.Search, contentDescription = "Search people") }
        IconButton(onClick = nav.onMessages) {
            BadgedBox(badge = { if (unread > 0) Badge { Text(if (unread > MAX_BADGE) "$MAX_BADGE+" else "$unread") } }) {
                Icon(Icons.AutoMirrored.Outlined.Send, contentDescription = "Messages")
            }
        }
        Spacer(Modifier.weight(1f))
        Text("Social", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 12.dp))
    }
}

/** The posts of any list, wired to its view model. */
fun LazyListScope.postItems(
    posts: List<FeedPost>,
    graph: AppGraph,
    vm: PostListViewModel,
    safety: FeedSafety,
    onProfile: (Int) -> Unit,
) {
    items(posts, key = { it.id }) { post ->
        var confirmDelete by remember { mutableStateOf(false) }
        SocialPostCard(
            post,
            baseUrl = graph.config.apiBaseUrl,
            now = rememberNow(),
            isMine = post.userId == safety.viewerId,
            actions = PostCallbacks(
                onKudos = vm::toggleKudos,
                onDoubleTap = vm::kudosByDoubleTap,
                onComments = { vm.openComments(it) },
                onShare = vm::share,
                onAuthor = onProfile,
                onDelete = { confirmDelete = true },
                onReport = { safety.vm.askReport(ReportKind.POST, it) },
                onBlock = { safety.vm.askBlock(it.userId, it.authorName) },
            ),
        )
        if (confirmDelete) {
            ConfirmDialog(
                title = "Delete this post?",
                body = "Its kudos and comments go with it. Your workouts stay saved.",
                confirm = "Delete",
                onConfirm = {
                    confirmDelete = false
                    vm.delete(post.id)
                },
                dismiss = "Cancel",
                onDismiss = { confirmDelete = false },
                destructive = true,
            )
        }
    }
}

/** The comments and share sheets every post list opens. */
@Composable
fun PostSheetsHost(vm: PostListViewModel, safety: FeedSafety) {
    val sheets by vm.sheets.collectAsStateWithLifecycle()
    ShareEffect(sheets.share, onShared = vm::shared)
    val postId = sheets.commentsPostId
    if (postId != null) {
        CommentsSheet(
            comments = sheets.comments,
            onAddComment = { vm.addComment(postId, it) },
            onDismiss = { vm.openComments(null) },
            safety = safety,
        )
    }
}

private const val LOAD_AHEAD = 3
private const val MAX_BADGE = 9
