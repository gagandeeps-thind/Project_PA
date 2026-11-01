package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.BlockEntry
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.FeedPostsData
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
import io.ktor.http.HttpMethod
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.serializer

/** The signed-in player: home screen, profile, progress, growth, social feed, privacy. */
@Suppress("TooManyFunctions")
class MeApi(private val api: ApiClient) {
    suspend fun today(lat: Double?, lng: Double?, utcOffsetMinutes: Int): TodayData =
        api.get("/api/v2/me/today", mapOf("lat" to lat, "lng" to lng, "utc_offset_minutes" to utcOffsetMinutes))

    suspend fun profile(): PlayerProfile = api.get("/api/v2/me/profile")

    suspend fun updateProfile(changes: JsonObject): PlayerProfile = api.put("/api/v2/me/profile", changes)

    suspend fun progression(): Progression = api.get("/api/v2/me/progression")

    suspend fun referrals(): ReferralSummary = api.get("/api/v2/me/referrals")

    suspend fun share(kind: String, entityId: Int): ShareCard =
        api.post("/api/v2/share", ApiClient.body("kind" to kind, "entity_id" to entityId))

    suspend fun notifications(): NotificationsData = api.get("/api/v2/me/notifications")

    suspend fun markNotificationRead(id: Int): NotificationItem =
        api.post("/api/v2/me/notifications/$id/read")

    suspend fun markAllNotificationsRead() =
        api.execute(HttpMethod.Post, "/api/v2/me/notifications/read-all")

    suspend fun suggestedChallenges(): List<SuggestedChallenge> =
        api.get("/api/v2/challenges/suggested")

    suspend fun suggestedOsirians(): List<SuggestedOsirian> =
        api.get("/api/v2/osirians/suggested")

    suspend fun trendingOsirians(): List<SuggestedOsirian> =
        api.get("/api/v2/osirians/trending")

    suspend fun followOsirian(userId: Int): FollowStatus =
        api.post("/api/v2/osirians/$userId/follow")

    suspend fun unfollowOsirian(userId: Int): FollowStatus =
        api.send(HttpMethod.Delete, "/api/v2/osirians/$userId/follow", emptyMap(), null, serializer())

    suspend fun dismissOsirian(userId: Int) =
        api.execute(HttpMethod.Post, "/api/v2/osirians/$userId/dismiss")

    suspend fun feedPosts(limit: Int, offset: Int): FeedPostsData =
        api.get("/api/v2/feed/posts", mapOf("limit" to limit, "offset" to offset))

    suspend fun createPost(draft: PostCreateDraft): FeedPost =
        api.postBody("/api/v2/feed/posts", draft)

    suspend fun reactToPost(postId: Int, reaction: String): FeedPost =
        api.post("/api/v2/feed/posts/$postId/react", ApiClient.body("reaction" to reaction))

    suspend fun postComments(postId: Int): List<PostCommentItem> =
        api.get("/api/v2/feed/posts/$postId/comments")

    suspend fun addPostComment(postId: Int, body: String): PostCommentItem =
        api.post("/api/v2/feed/posts/$postId/comments", ApiClient.body("body" to body))

    suspend fun sharePost(postId: Int): PostShareResult =
        api.post("/api/v2/feed/posts/$postId/share")

    suspend fun track(event: String, installId: String?, properties: Map<String, String>) =
        api.execute(
            HttpMethod.Post,
            "/api/v2/events",
            ApiClient.body("event_name" to event, "install_id" to installId, "properties" to properties),
        )

    suspend fun blocks(): List<BlockEntry> = api.get("/api/v2/me/blocks")

    suspend fun unblock(blockId: Int) = api.execute(HttpMethod.Delete, "/api/v2/blocks/$blockId")

    suspend fun export(): JsonObject = api.get("/api/v2/me/export")

    suspend fun erase(password: String) =
        api.execute(HttpMethod.Post, "/api/v2/me/erase", ApiClient.body("password" to password, "confirm" to "DELETE"))

    suspend fun rules(): JsonObject = api.get("/api/v2/rules")
}
