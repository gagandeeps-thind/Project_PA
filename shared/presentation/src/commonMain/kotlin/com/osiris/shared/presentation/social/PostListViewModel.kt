package com.osiris.shared.presentation.social

import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.PostCommentItem
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.SocialRepository
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.ShareRequest
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The comments sheet and share sheet any list of posts can open. */
data class PostSheets(
    val commentsPostId: Int? = null,
    val comments: List<PostCommentItem> = emptyList(),
    val share: ShareRequest? = null,
)

/**
 * What every list of posts can do: kudos (the fire reaction, Instagram's heart), comment, share and
 * delete your own. Subclasses own the list; this edits it through [editPosts].
 */
abstract class PostListViewModel(
    protected val player: PlayerRepository,
    protected val social: SocialRepository,
    dispatcher: CoroutineDispatcher,
) : SharedViewModel(dispatcher) {
    private val _sheets = MutableStateFlow(PostSheets())
    val sheets: StateFlow<PostSheets> = _sheets.asStateFlow()

    protected abstract fun posts(): List<FeedPost>
    protected abstract fun editPosts(edit: (List<FeedPost>) -> List<FeedPost>)

    private fun replace(post: FeedPost) = editPosts { list -> list.map { if (it.id == post.id) post else it } }

    /** Toggles kudos at once and reconciles with the server; a failure puts the post back. */
    fun toggleKudos(postId: Int) {
        val before = posts().firstOrNull { it.id == postId } ?: return
        replace(before.withKudosToggled())
        scope.launch {
            val updated = player.reactToPost(postId, KUDOS).orShow()
            replace(updated ?: before)
        }
    }

    /** Double-tap only ever adds kudos, like Instagram's double-tap heart. */
    fun kudosByDoubleTap(postId: Int) {
        val post = posts().firstOrNull { it.id == postId } ?: return
        if (post.myReaction != KUDOS) toggleKudos(postId)
    }

    fun openComments(postId: Int?) {
        val initial = posts().firstOrNull { it.id == postId }?.recentComments.orEmpty()
        _sheets.update { it.copy(commentsPostId = postId, comments = initial) }
        if (postId == null) return
        scope.launch {
            val all = player.postComments(postId).orShow() ?: return@launch
            _sheets.update { if (it.commentsPostId == postId) it.copy(comments = all) else it }
        }
    }

    fun addComment(postId: Int, body: String) {
        val text = body.trim()
        if (text.isEmpty()) return
        scope.launch {
            val added = player.addPostComment(postId, text).orShow() ?: return@launch
            editPosts { list ->
                list.map {
                    if (it.id == postId) {
                        it.copy(commentCount = it.commentCount + 1, recentComments = (it.recentComments + added).takeLast(PREVIEW))
                    } else {
                        it
                    }
                }
            }
            _sheets.update { if (it.commentsPostId == postId) it.copy(comments = it.comments + added) else it }
        }
    }

    fun share(postId: Int) {
        scope.launch {
            val res = player.sharePost(postId).orShow() ?: return@launch
            editPosts { list -> list.map { if (it.id == postId) it.copy(shareCount = res.shareCount) else it } }
            _sheets.update { it.copy(share = ShareRequest("${res.shareText} ${res.shareUrl}".trim(), "social_post")) }
        }
    }

    fun shared(completed: Boolean) {
        val kind = _sheets.value.share?.kind
        _sheets.update { it.copy(share = null) }
        if (completed && kind != null) scope.launch { player.track("share_completed", mapOf("kind" to kind)) }
    }

    fun delete(postId: Int) {
        scope.launch {
            social.deletePost(postId).orShow() ?: return@launch
            editPosts { list -> list.filterNot { it.id == postId } }
            show("Post deleted", UiMessage.Kind.SUCCESS)
        }
    }

    companion object {
        const val KUDOS = "fire"
        private const val PREVIEW = 3
    }
}

/** The post as it reads right after tapping kudos, before the server answers. */
internal fun FeedPost.withKudosToggled(): FeedPost {
    val kudos = PostListViewModel.KUDOS
    val counts = reactions.toMutableMap()
    myReaction?.let { counts[it] = ((counts[it] ?: 0) - 1).coerceAtLeast(0) }
    val adding = myReaction != kudos
    if (adding) counts[kudos] = (counts[kudos] ?: 0) + 1
    return copy(
        reactions = counts.filterValues { it > 0 },
        myReaction = if (adding) kudos else null,
        totalReactions = counts.values.sum(),
    )
}
