package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.DiscoverPage
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.Inbox
import com.osiris.shared.domain.model.MessageThread
import com.osiris.shared.domain.model.SocialFeedPage
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.domain.model.SocialUser

/** The Social tab: following feed, discover, people search, profiles, posting and direct messages. */
interface SocialRepository {
    suspend fun feed(beforeId: Int? = null): Outcome<SocialFeedPage>
    suspend fun discover(activity: String? = null, offset: Int = 0): Outcome<DiscoverPage>
    suspend fun search(query: String): Outcome<List<SocialUser>>
    suspend fun profile(userId: Int): Outcome<SocialProfile>
    suspend fun createPost(draft: SocialPostDraft): Outcome<FeedPost>
    suspend fun deletePost(postId: Int): Outcome<Unit>
    suspend fun inbox(): Outcome<Inbox>
    suspend fun thread(userId: Int, beforeId: Int? = null): Outcome<MessageThread>
    suspend fun send(userId: Int, body: String): Outcome<DirectMessage>
    suspend fun markRead(userId: Int): Outcome<Inbox>
}
