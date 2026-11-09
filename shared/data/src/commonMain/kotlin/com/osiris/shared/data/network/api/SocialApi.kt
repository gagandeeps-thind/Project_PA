package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.DiscoverPage
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.Inbox
import com.osiris.shared.domain.model.MessageResponse
import com.osiris.shared.domain.model.MessageThread
import com.osiris.shared.domain.model.SocialFeedPage
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.domain.model.SocialUser
import io.ktor.http.HttpMethod

/** The Social tab (`/api/v2/social/...`). */
class SocialApi(private val api: ApiClient) {
    suspend fun feed(beforeId: Int?): SocialFeedPage =
        api.get("/api/v2/social/feed", mapOf("limit" to PAGE, "before_id" to beforeId))

    suspend fun discover(activity: String?, offset: Int): DiscoverPage =
        api.get("/api/v2/social/discover", mapOf("limit" to PAGE, "offset" to offset, "activity" to activity))

    suspend fun search(query: String): List<SocialUser> = api.get("/api/v2/social/search", mapOf("q" to query))

    suspend fun profile(userId: Int): SocialProfile = api.get("/api/v2/social/users/$userId")

    suspend fun createPost(draft: SocialPostDraft): FeedPost = api.postBody("/api/v2/social/posts", draft)

    suspend fun deletePost(postId: Int) = api.execute(HttpMethod.Delete, "/api/v2/social/posts/$postId")

    suspend fun inbox(): Inbox = api.get("/api/v2/social/conversations")

    suspend fun thread(userId: Int, beforeId: Int?): MessageThread =
        api.get("/api/v2/social/conversations/$userId/messages", mapOf("before_id" to beforeId))

    suspend fun send(userId: Int, body: String): DirectMessage =
        api.post("/api/v2/social/conversations/$userId/messages", ApiClient.body("body" to body))

    suspend fun markRead(userId: Int): Inbox = api.post("/api/v2/social/conversations/$userId/read")

    suspend fun report(targetType: String, targetId: Int, reason: String): MessageResponse =
        api.post("/api/v2/reports", ApiClient.body("target_type" to targetType, "target_id" to targetId, "reason" to reason))

    suspend fun block(userId: Int) = api.execute(HttpMethod.Post, "/api/v2/blocks", ApiClient.body("user_id" to userId))

    private companion object {
        const val PAGE = 20
    }
}
