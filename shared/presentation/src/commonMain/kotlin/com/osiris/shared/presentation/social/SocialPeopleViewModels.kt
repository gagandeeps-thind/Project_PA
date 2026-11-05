package com.osiris.shared.presentation.social

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SocialSearchState(
    val query: String = "",
    /** null until the player has typed enough to search. */
    val results: Loadable<List<SocialUser>>? = null,
) {
    val tooShort: Boolean get() = query.trim().length < SocialSearchViewModel.MIN_QUERY
}

/** People search by name or handle, as the player types. */
class SocialSearchViewModel(
    private val social: SocialRepository,
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    private val debounceMs: Long = DEBOUNCE_MS,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(SocialSearchState())
    val state: StateFlow<SocialSearchState> = _state.asStateFlow()
    private var searching: Job? = null

    fun query(text: String) {
        _state.update { it.copy(query = text) }
        searching?.cancel()
        if (_state.value.tooShort) {
            _state.update { it.copy(results = null) }
            return
        }
        _state.update { it.copy(results = it.results ?: Loadable.Loading) }
        searching = scope.launch {
            delay(debounceMs)
            val result = social.search(text)
            _state.update { if (it.query == text) it.copy(results = Loadable.of(result)) else it }
        }
    }

    /** Follow or unfollow from a result row, at once; a failure flips it back. */
    fun toggleFollow(userId: Int) {
        val row = _state.value.results?.valueOrNull?.firstOrNull { it.userId == userId } ?: return
        val following = !row.following
        setFollowing(userId, following)
        scope.launch {
            val result = if (following) player.followOsirian(userId) else player.unfollowOsirian(userId)
            if (result.orShow() == null) setFollowing(userId, !following)
        }
    }

    private fun setFollowing(userId: Int, following: Boolean) = _state.update { s ->
        val list = s.results?.valueOrNull ?: return@update s
        s.copy(results = Loadable.Ready(list.map { if (it.userId == userId) it.copy(following = following) else it }))
    }

    companion object {
        const val MIN_QUERY = 2
        const val DEBOUNCE_MS = 300L
    }
}

data class SocialProfileState(
    val profile: Loadable<SocialProfile> = Loadable.Loading,
    val followBusy: Boolean = false,
)

/** A player's profile: counts, this week's training, and their posts. */
class SocialProfileViewModel(
    private val userId: Int,
    player: PlayerRepository,
    social: SocialRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : PostListViewModel(player, social, dispatcher) {
    private val _state = MutableStateFlow(SocialProfileState())
    val state: StateFlow<SocialProfileState> = _state.asStateFlow()

    init {
        refresh()
    }

    override fun posts(): List<FeedPost> = _state.value.profile.valueOrNull?.posts.orEmpty()

    override fun editPosts(edit: (List<FeedPost>) -> List<FeedPost>) = _state.update { s ->
        val p = s.profile.valueOrNull ?: return@update s
        val posts = edit(p.posts)
        s.copy(profile = Loadable.Ready(p.copy(posts = posts, postsCount = p.postsCount - (p.posts.size - posts.size))))
    }

    fun refresh() {
        scope.launch {
            val result = social.profile(userId)
            // A failed refresh keeps the profile on screen and says why.
            if (result is Outcome.Failure && _state.value.profile is Loadable.Ready) {
                showError(result.error)
            } else {
                _state.update { it.copy(profile = Loadable.of(result)) }
            }
        }
    }

    fun toggleFollow() {
        val p = _state.value.profile.valueOrNull ?: return
        if (p.isMe || _state.value.followBusy) return
        _state.update { it.copy(followBusy = true) }
        scope.launch {
            val status = (if (p.user.following) player.unfollowOsirian(userId) else player.followOsirian(userId)).orShow()
            _state.update { s ->
                val cur = s.profile.valueOrNull
                if (status == null || cur == null) return@update s.copy(followBusy = false)
                s.copy(
                    followBusy = false,
                    profile = Loadable.Ready(
                        cur.copy(
                            user = cur.user.copy(following = status.following),
                            followersCount = status.followersCount,
                            // Messaging needs a follow either way; following someone opens it.
                            canMessage = status.following || cur.user.followsMe,
                        ),
                    ),
                )
            }
        }
    }
}
