package com.osiris.shared.presentation.today

import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.NotificationItem
import com.osiris.shared.domain.model.PostCommentItem
import com.osiris.shared.domain.model.PostCreateDraft
import com.osiris.shared.domain.model.SuggestedChallenge
import com.osiris.shared.domain.model.SuggestedOsirian
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.model.WorkoutPlan
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.ShareRequest
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

data class HomeScreenState(
    val today: Loadable<TodayData> = Loadable.Loading,
    val unreadNotifications: Int = 0,
    val notifications: List<NotificationItem> = emptyList(),
    val notificationsOpen: Boolean = false,
    val suggestedChallenges: List<SuggestedChallenge> = emptyList(),
    val joiningChallengeId: Int? = null,
    val workoutPlan: WorkoutPlan = WorkoutPlan(),
    val workoutCustomizerOpen: Boolean = false,
    val suggestedOsirians: List<SuggestedOsirian> = emptyList(),
    val trendingOsirians: List<SuggestedOsirian> = emptyList(),
    val trendingSheetOpen: Boolean = false,
    val feedPosts: List<FeedPost> = emptyList(),
    val postComposerOpen: Boolean = false,
    val activeCommentsPostId: Int? = null,
    val activePostComments: List<PostCommentItem> = emptyList(),
    val share: ShareRequest? = null,
)

/**
 * Home screen: top-right notifications, circular-floating Suggested Challenges deck,
 * Streak Start workout customizer, Today's quest + week strip, Suggested Osirians carousel,
 * and People's Posts social feed.
 */
@Suppress("TooManyFunctions")
class TodayViewModel(
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    private val challenges: ChallengeRepository? = null,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow<Loadable<TodayData>>(Loadable.Loading)
    val state: StateFlow<Loadable<TodayData>> = _state.asStateFlow()

    private val _home = MutableStateFlow(HomeScreenState())
    val home: StateFlow<HomeScreenState> = _home.asStateFlow()

    /** Used only to suggest a nearby starter challenge; never stored. */
    private var position: LatLng? = null
    private var loading: Job? = null

    /** The first load waits briefly for a position, so opening the app asks for Today once, not twice. */
    private val firstPosition = CompletableDeferred<LatLng?>()

    init {
        scope.launch { player.track("app_opened") }
        loading = scope.launch {
            position = withTimeoutOrNull(POSITION_GRACE_MS) { firstPosition.await() }
            firstPosition.complete(null)
            load()
        }
    }

    /** The platform reports one position when it has one; without it only the suggestion is skipped. */
    fun onPosition(position: LatLng) {
        if (firstPosition.complete(position)) return
        if (this.position == position) return
        this.position = position
        refresh()
    }

    /** No permission or no fix: the first load need not wait for one. */
    fun onNoPosition() {
        firstPosition.complete(null)
    }

    fun refresh() {
        firstPosition.complete(null)
        loading?.cancel()
        if (_state.value !is Loadable.Ready) {
            _state.value = Loadable.Loading
            _home.update { it.copy(today = Loadable.Loading) }
        }
        loading = scope.launch { load() }
    }

    private suspend fun load() {
        val result = player.today(position)
        val current = _state.value
        val next = if (result.isSuccess || current !is Loadable.Ready) Loadable.of(result) else current.also {
            result.errorOrNull()?.let(::showError)
        }
        _state.value = next
        _home.update { it.copy(today = next) }
        if (next is Loadable.Ready) {
            loadHomeExtras()
        }
    }

    private suspend fun loadHomeExtras() {
        player.notifications().getOrNull()?.let { data ->
            _home.update { it.copy(unreadNotifications = data.unreadCount, notifications = data.items) }
        }
        player.suggestedChallenges().getOrNull()?.let { list ->
            _home.update { it.copy(suggestedChallenges = list) }
        }
        player.suggestedOsirians().getOrNull()?.let { list ->
            _home.update { it.copy(suggestedOsirians = list) }
        }
        player.feedPosts().getOrNull()?.let { posts ->
            _home.update { it.copy(feedPosts = posts) }
        }
    }

    fun grantLocationConsent() {
        scope.launch {
            player.updateProfile(buildJsonObject { put("location_consent", JsonPrimitive(true)) }).orShow() ?: return@launch
            refresh()
        }
    }

    fun onStartQuest() {
        scope.launch { player.track("run_started", mapOf("source" to "today")) }
    }

    // --- Notifications ---------------------------------------------------------------

    fun openNotifications(open: Boolean) {
        _home.update { it.copy(notificationsOpen = open) }
        if (open) {
            scope.launch {
                player.notifications().getOrNull()?.let { data ->
                    _home.update { it.copy(unreadNotifications = data.unreadCount, notifications = data.items) }
                }
            }
        }
    }

    fun markNotificationRead(id: Int) {
        scope.launch {
            val updated = player.markNotificationRead(id).orShow() ?: return@launch
            _home.update { s ->
                val list = s.notifications.map { if (it.id == id) updated else it }
                s.copy(notifications = list, unreadNotifications = list.count { !it.read })
            }
        }
    }

    fun markAllNotificationsRead() {
        scope.launch {
            player.markAllNotificationsRead().orShow() ?: return@launch
            _home.update { s ->
                s.copy(
                    notifications = s.notifications.map { it.copy(read = true) },
                    unreadNotifications = 0,
                )
            }
        }
    }

    // --- Suggested Global Challenges (Circular-Floating Card Deck) -------------------

    fun joinSuggestedChallenge(challengeId: Int) {
        if (_home.value.joiningChallengeId != null) return
        _home.update { it.copy(joiningChallengeId = challengeId) }
        scope.launch {
            val ok = challenges?.join(challengeId)?.orShow() != null || challenges == null
            _home.update { s ->
                val updated = if (ok) {
                    s.suggestedChallenges.map { c ->
                        if (c.id == challengeId && !c.joined) {
                            c.copy(joined = true, participants = c.participants + 1)
                        } else {
                            c
                        }
                    }
                } else {
                    s.suggestedChallenges
                }
                s.copy(joiningChallengeId = null, suggestedChallenges = updated)
            }
            if (ok) {
                player.track("suggested_challenge_joined", mapOf("challenge_id" to challengeId.toString()))
                show("Challenge joined! Ready to start.", UiMessage.Kind.SUCCESS)
            }
        }
    }

    // --- Streak Start & Workout Customizer -------------------------------------------

    fun openWorkoutCustomizer(open: Boolean) {
        _home.update { it.copy(workoutCustomizerOpen = open) }
    }

    fun selectWorkoutOption(key: String) {
        _home.update { it.copy(workoutPlan = it.workoutPlan.copy(optionKey = key)) }
    }

    fun setWorkoutReps(reps: Int) {
        _home.update { it.copy(workoutPlan = it.workoutPlan.copy(repsPerSet = reps.coerceIn(1, MAX_REPS_PER_SET))) }
    }

    fun setWorkoutSets(sets: Int) {
        _home.update { it.copy(workoutPlan = it.workoutPlan.copy(sets = sets.coerceIn(1, MAX_SETS))) }
    }

    fun setWorkoutHoldSeconds(seconds: Int) {
        _home.update { it.copy(workoutPlan = it.workoutPlan.copy(holdSecondsPerSet = seconds.coerceIn(MIN_HOLD_S, MAX_HOLD_S))) }
    }

    fun setWorkoutDistanceKm(km: Double) {
        _home.update { it.copy(workoutPlan = it.workoutPlan.copy(targetDistanceKm = km.coerceIn(MIN_DISTANCE_KM, MAX_DISTANCE_KM))) }
    }

    // --- Suggested Osirians & Trending ("See All") -----------------------------------

    fun followOsirian(userId: Int) {
        scope.launch {
            val status = player.followOsirian(userId).orShow() ?: return@launch
            _home.update { s ->
                s.copy(
                    suggestedOsirians = s.suggestedOsirians.map {
                        if (it.userId == userId) it.copy(following = status.following, followersCount = status.followersCount) else it
                    },
                    trendingOsirians = s.trendingOsirians.map {
                        if (it.userId == userId) it.copy(following = status.following, followersCount = status.followersCount) else it
                    },
                )
            }
        }
    }

    fun unfollowOsirian(userId: Int) {
        scope.launch {
            val status = player.unfollowOsirian(userId).orShow() ?: return@launch
            _home.update { s ->
                s.copy(
                    suggestedOsirians = s.suggestedOsirians.map {
                        if (it.userId == userId) it.copy(following = status.following, followersCount = status.followersCount) else it
                    },
                    trendingOsirians = s.trendingOsirians.map {
                        if (it.userId == userId) it.copy(following = status.following, followersCount = status.followersCount) else it
                    },
                )
            }
        }
    }

    fun dismissOsirian(userId: Int) {
        _home.update { s -> s.copy(suggestedOsirians = s.suggestedOsirians.filterNot { it.userId == userId }) }
        scope.launch {
            player.dismissOsirian(userId)
        }
    }

    fun openTrendingOsirians(open: Boolean) {
        _home.update { it.copy(trendingSheetOpen = open) }
        if (open) {
            scope.launch {
                val list = player.trendingOsirians().orShow() ?: return@launch
                _home.update { it.copy(trendingOsirians = list) }
            }
        }
    }

    // --- People's Posts Social Feed --------------------------------------------------

    fun openPostComposer(open: Boolean) {
        _home.update { it.copy(postComposerOpen = open) }
    }

    fun publishPost(draft: PostCreateDraft) {
        scope.launch {
            val created = player.createPost(draft).orShow() ?: return@launch
            _home.update { s ->
                s.copy(postComposerOpen = false, feedPosts = listOf(created) + s.feedPosts)
            }
            show("Posted to People's Posts!", UiMessage.Kind.SUCCESS)
        }
    }

    fun reactToPost(postId: Int, reaction: String) {
        scope.launch {
            val updated = player.reactToPost(postId, reaction).orShow() ?: return@launch
            _home.update { s ->
                s.copy(feedPosts = s.feedPosts.map { if (it.id == postId) updated else it })
            }
        }
    }

    fun openComments(postId: Int?) {
        _home.update { s ->
            val initial = s.feedPosts.firstOrNull { it.id == postId }?.recentComments.orEmpty()
            s.copy(activeCommentsPostId = postId, activePostComments = initial)
        }
        if (postId != null) {
            scope.launch {
                val all = player.postComments(postId).orShow() ?: return@launch
                _home.update { s ->
                    if (s.activeCommentsPostId == postId) s.copy(activePostComments = all) else s
                }
            }
        }
    }

    fun addComment(postId: Int, body: String) {
        val trimmed = body.trim()
        if (trimmed.isEmpty()) return
        scope.launch {
            val added = player.addPostComment(postId, trimmed).orShow() ?: return@launch
            _home.update { s ->
                val updatedPosts = s.feedPosts.map { p ->
                    if (p.id == postId) {
                        p.copy(
                            commentCount = p.commentCount + 1,
                            recentComments = (p.recentComments + added).takeLast(RECENT_COMMENTS_PREVIEW),
                        )
                    } else {
                        p
                    }
                }
                s.copy(
                    feedPosts = updatedPosts,
                    activePostComments = if (s.activeCommentsPostId == postId) s.activePostComments + added else s.activePostComments,
                )
            }
        }
    }

    fun sharePost(postId: Int) {
        scope.launch {
            val res = player.sharePost(postId).orShow() ?: return@launch
            _home.update { s ->
                s.copy(
                    feedPosts = s.feedPosts.map { if (it.id == postId) it.copy(shareCount = res.shareCount) else it },
                    share = ShareRequest("${res.shareText} ${res.shareUrl}".trim(), "feed_post"),
                )
            }
        }
    }

    fun shared(completed: Boolean) {
        val kind = _home.value.share?.kind
        _home.update { it.copy(share = null) }
        if (completed && kind != null) {
            scope.launch { player.track("share_completed", mapOf("kind" to kind)) }
        }
    }

    companion object {
        /** A cached or network fix usually arrives well inside this; after it Today loads without one. */
        const val POSITION_GRACE_MS = 1_000L
        private const val MAX_REPS_PER_SET = 200
        private const val MAX_SETS = 20
        private const val MIN_HOLD_S = 10
        private const val MAX_HOLD_S = 600
        private const val MIN_DISTANCE_KM = 0.5
        private const val MAX_DISTANCE_KM = 50.0
        private const val RECENT_COMMENTS_PREVIEW = 3
    }
}
