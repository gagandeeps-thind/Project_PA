package com.osiris.shared.presentation.social

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.ActiveFriend
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.Loadable
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SocialFeedState(
    val activeToday: List<ActiveFriend> = emptyList(),
    val posts: Loadable<List<FeedPost>> = Loadable.Loading,
    val nextBeforeId: Int? = null,
    val loadingMore: Boolean = false,
    val refreshing: Boolean = false,
    val unreadMessages: Int = 0,
) {
    val canLoadMore: Boolean get() = nextBeforeId != null && !loadingMore
}

/** The Social tab's home: posts by people you follow, newest first, and who trained today. */
class SocialFeedViewModel(
    player: PlayerRepository,
    social: SocialRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : PostListViewModel(player, social, dispatcher) {
    private val _state = MutableStateFlow(SocialFeedState())
    val state: StateFlow<SocialFeedState> = _state.asStateFlow()
    private var loading: Job? = null

    init {
        refresh()
    }

    override fun posts(): List<FeedPost> = _state.value.posts.valueOrNull.orEmpty()

    override fun editPosts(edit: (List<FeedPost>) -> List<FeedPost>) = _state.update { s ->
        val list = s.posts.valueOrNull ?: return@update s
        s.copy(posts = Loadable.Ready(edit(list)))
    }

    /** Reloads the first page. A loaded feed stays on screen while it refreshes. */
    fun refresh() {
        loading?.cancel()
        _state.update { it.copy(refreshing = it.posts is Loadable.Ready, loadingMore = false) }
        loading = scope.launch {
            val inbox = async { social.inbox() }
            val page = social.feed()
            val unread = (inbox.await() as? Outcome.Success)?.value?.unreadTotal ?: _state.value.unreadMessages
            _state.update { s ->
                when (page) {
                    is Outcome.Success -> s.copy(
                        activeToday = page.value.activeToday, posts = Loadable.Ready(page.value.items),
                        nextBeforeId = page.value.nextBeforeId, refreshing = false, unreadMessages = unread,
                    )
                    // A failed refresh keeps what is already shown and says why.
                    is Outcome.Failure -> if (s.posts is Loadable.Ready) {
                        showError(page.error)
                        s.copy(refreshing = false, unreadMessages = unread)
                    } else {
                        s.copy(posts = Loadable.failed(page.error), refreshing = false, unreadMessages = unread)
                    }
                }
            }
        }
    }

    fun loadMore() {
        val s = _state.value
        val before = s.nextBeforeId
        if (before == null || s.loadingMore || s.posts !is Loadable.Ready) return
        _state.update { it.copy(loadingMore = true) }
        loading = scope.launch {
            val page = social.feed(before).orShow()
            _state.update { cur ->
                if (page == null) return@update cur.copy(loadingMore = false)
                val have = cur.posts.valueOrNull.orEmpty()
                val known = have.map { it.id }.toSet()
                cur.copy(
                    posts = Loadable.Ready(have + page.items.filterNot { it.id in known }),
                    nextBeforeId = page.nextBeforeId, loadingMore = false,
                )
            }
        }
    }

    /** Puts a post the player just made at the top without a reload. */
    fun prepend(post: FeedPost) = editPosts { list -> listOf(post) + list.filterNot { it.id == post.id } }
}
