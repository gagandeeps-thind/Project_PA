package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.core.logging.Logger
import com.osiris.shared.data.network.api.MeApi
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.FollowStatus
import com.osiris.shared.domain.model.NotificationItem
import com.osiris.shared.domain.model.NotificationsData
import com.osiris.shared.domain.model.PlayerProfile
import com.osiris.shared.domain.model.PostCommentItem
import com.osiris.shared.domain.model.PostCreateDraft
import com.osiris.shared.domain.model.PostShareResult
import com.osiris.shared.domain.model.Progression
import com.osiris.shared.domain.model.ReferralSummary
import com.osiris.shared.domain.model.ShareCard
import com.osiris.shared.domain.model.SuggestedChallenge
import com.osiris.shared.domain.model.SuggestedOsirian
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.run.LatLng
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Clock
import kotlinx.serialization.json.JsonObject

@Suppress("TooManyFunctions")
class PlayerRepositoryImpl(
    private val me: MeApi,
    private val installId: InstallId,
    private val logger: Logger,
    private val clock: Clock = Clock.System,
) : PlayerRepository {
    override suspend fun today(position: LatLng?): Outcome<TodayData> = outcomeOf {
        me.today(position?.lat, position?.lng, utcOffsetMinutes(clock.now()))
    }

    override suspend fun profile(): Outcome<PlayerProfile> = outcomeOf { me.profile() }

    override suspend fun updateProfile(changes: JsonObject): Outcome<PlayerProfile> = outcomeOf { me.updateProfile(changes) }

    override suspend fun progression(): Outcome<Progression> = outcomeOf { me.progression() }

    override suspend fun referrals(): Outcome<ReferralSummary> = outcomeOf { me.referrals() }

    override suspend fun shareAchievement(kind: String, entityId: Int): Outcome<ShareCard> = outcomeOf {
        val card = me.share(kind, entityId)
        track("share_completed", mapOf("kind" to kind))
        card
    }

    override suspend fun notifications(): Outcome<NotificationsData> = outcomeOf { me.notifications() }

    override suspend fun markNotificationRead(id: Int): Outcome<NotificationItem> = outcomeOf {
        me.markNotificationRead(id)
    }

    override suspend fun markAllNotificationsRead(): Outcome<Unit> = outcomeOf { me.markAllNotificationsRead() }

    override suspend fun suggestedChallenges(): Outcome<List<SuggestedChallenge>> = outcomeOf {
        me.suggestedChallenges()
    }

    override suspend fun suggestedOsirians(): Outcome<List<SuggestedOsirian>> = outcomeOf {
        me.suggestedOsirians()
    }

    override suspend fun trendingOsirians(): Outcome<List<SuggestedOsirian>> = outcomeOf {
        me.trendingOsirians()
    }

    override suspend fun followOsirian(userId: Int): Outcome<FollowStatus> = outcomeOf {
        me.followOsirian(userId)
    }

    override suspend fun unfollowOsirian(userId: Int): Outcome<FollowStatus> = outcomeOf {
        me.unfollowOsirian(userId)
    }

    override suspend fun dismissOsirian(userId: Int): Outcome<Unit> = outcomeOf {
        me.dismissOsirian(userId)
    }

    override suspend fun feedPosts(limit: Int, offset: Int): Outcome<List<FeedPost>> = outcomeOf {
        me.feedPosts(limit, offset).items
    }

    override suspend fun createPost(draft: PostCreateDraft): Outcome<FeedPost> = outcomeOf {
        me.createPost(draft)
    }

    override suspend fun reactToPost(postId: Int, reaction: String): Outcome<FeedPost> = outcomeOf {
        me.reactToPost(postId, reaction)
    }

    override suspend fun postComments(postId: Int): Outcome<List<PostCommentItem>> = outcomeOf {
        me.postComments(postId)
    }

    override suspend fun addPostComment(postId: Int, body: String): Outcome<PostCommentItem> = outcomeOf {
        me.addPostComment(postId, body)
    }

    override suspend fun sharePost(postId: Int): Outcome<PostShareResult> = outcomeOf {
        me.sharePost(postId)
    }

    override suspend fun track(event: String, properties: Map<String, String>) {
        try {
            me.track(event, installId.get(), properties)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            logger.debug(TAG, "Event $event not sent: ${e.message}")
        }
    }

    private companion object {
        const val TAG = "OsirisPlayer"
    }
}
