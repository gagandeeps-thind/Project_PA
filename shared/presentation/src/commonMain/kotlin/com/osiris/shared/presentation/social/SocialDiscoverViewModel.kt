package com.osiris.shared.presentation.social

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.Loadable
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SocialDiscoverState(
    /** Activity keys the player trains most, from the server; the filter chips lead with them. */
    val interests: List<String> = emptyList(),
    /** null is "For you". */
    val activity: String? = null,
    val posts: Loadable<List<FeedPost>> = Loadable.Loading,
    val followed: Set<Int> = emptySet(),
    val openPostId: Int? = null,
    val loadingMore: Boolean = false,
    val endReached: Boolean = false,
) {
    /** Interests first, then popular activities, without repeats. */
    val chips: List<String> get() = (interests + POPULAR).distinct()

    val openPost: FeedPost? get() = posts.valueOrNull?.firstOrNull { it.id == openPostId }

    companion object {
        val POPULAR = listOf("run", "cycle", "walk", "strength", "hiit", "pushup", "squat", "swim")
    }
}

/** Discover: suggested posts from people you don't follow, ranked by what you train. */
class SocialDiscoverViewModel(
    player: PlayerRepository,
    social: SocialRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : PostListViewModel(player, social, dispatcher) {
    private val _state = MutableStateFlow(SocialDiscoverState())
    val state: StateFlow<SocialDiscoverState> = _state.asStateFlow()
    private var loading: Job? = null

    init {
        refresh()
    }

    override fun posts(): List<FeedPost> = _state.value.posts.valueOrNull.orEmpty()

    override fun editPosts(edit: (List<FeedPost>) -> List<FeedPost>) = _state.update { s ->
        val list = s.posts.valueOrNull ?: return@update s
        s.copy(posts = Loadable.Ready(edit(list)))
    }

    fun select(activity: String?) {
        if (activity == _state.value.activity) return
        _state.update { it.copy(activity = activity, posts = Loadable.Loading, openPostId = null) }
        refresh()
    }

    fun refresh() {
        loading?.cancel()
        val activity = _state.value.activity
        loading = scope.launch {
            val page = social.discover(activity)
            _state.update { s ->
                when (page) {
                    is Outcome.Success -> s.copy(
                        interests = page.value.interests, posts = Loadable.Ready(page.value.items),
                        endReached = page.value.items.size < PAGE, loadingMore = false,
                    )
                    is Outcome.Failure -> s.copy(posts = Loadable.failed(page.error), loadingMore = false)
                }
            }
        }
    }

    fun loadMore() {
        val s = _state.value
        val have = s.posts.valueOrNull ?: return
        if (s.loadingMore || s.endReached) return
        _state.update { it.copy(loadingMore = true) }
        loading = scope.launch {
            val page = social.discover(s.activity, offset = have.size).orShow()
            _state.update { cur ->
                if (page == null) return@update cur.copy(loadingMore = false)
                val known = cur.posts.valueOrNull.orEmpty().map { it.id }.toSet()
                cur.copy(
                    posts = Loadable.Ready(cur.posts.valueOrNull.orEmpty() + page.items.filterNot { it.id in known }),
                    loadingMore = false, endReached = page.items.size < PAGE,
                )
            }
        }
    }

    fun open(postId: Int?) = _state.update { it.copy(openPostId = postId) }

    /** Follows the post's author from Discover; their posts then move to the following feed. */
    fun follow(userId: Int) {
        if (userId in _state.value.followed) return
        _state.update { it.copy(followed = it.followed + userId) }
        scope.launch {
            if (player.followOsirian(userId).orShow() == null) _state.update { it.copy(followed = it.followed - userId) }
        }
    }

    private companion object {
        const val PAGE = 20
    }
}
