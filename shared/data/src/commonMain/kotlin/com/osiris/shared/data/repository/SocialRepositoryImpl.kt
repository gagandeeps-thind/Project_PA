package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.SocialApi
import com.osiris.shared.domain.model.ContentReportReason
import com.osiris.shared.domain.model.DirectMessage
import com.osiris.shared.domain.model.DiscoverPage
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.Inbox
import com.osiris.shared.domain.model.MessageThread
import com.osiris.shared.domain.model.ReportTarget
import com.osiris.shared.domain.model.SocialFeedPage
import com.osiris.shared.domain.model.SocialPostDraft
import com.osiris.shared.domain.model.SocialProfile
import com.osiris.shared.domain.model.SocialUser
import com.osiris.shared.domain.repository.SocialRepository

class SocialRepositoryImpl(private val api: SocialApi) : SocialRepository {
    override suspend fun feed(beforeId: Int?): Outcome<SocialFeedPage> = outcomeOf { api.feed(beforeId) }

    override suspend fun discover(activity: String?, offset: Int): Outcome<DiscoverPage> =
        outcomeOf { api.discover(activity?.takeIf { it.isNotBlank() }, offset) }

    override suspend fun search(query: String): Outcome<List<SocialUser>> = outcomeOf {
        val q = query.trim()
        if (q.length < MIN_QUERY) emptyList() else api.search(q)
    }

    override suspend fun profile(userId: Int): Outcome<SocialProfile> = outcomeOf { api.profile(userId) }

    override suspend fun createPost(draft: SocialPostDraft): Outcome<FeedPost> = outcomeOf {
        if (draft.isEmpty) throw AppError.Validation("Add a photo, a workout, a chart or a caption.")
        if (draft.trainingSessionIds.size > SocialPostDraft.MAX_WORKOUTS) {
            throw AppError.Validation("Attach at most ${SocialPostDraft.MAX_WORKOUTS} workouts.")
        }
        api.createPost(draft.copy(caption = draft.caption.trim()))
    }

    override suspend fun deletePost(postId: Int): Outcome<Unit> = outcomeOf { api.deletePost(postId) }

    override suspend fun inbox(): Outcome<Inbox> = outcomeOf { api.inbox() }

    override suspend fun thread(userId: Int, beforeId: Int?): Outcome<MessageThread> =
        outcomeOf { api.thread(userId, beforeId) }

    override suspend fun send(userId: Int, body: String): Outcome<DirectMessage> = outcomeOf {
        val text = body.trim()
        if (text.isEmpty()) throw AppError.Validation("Write a message first.")
        if (text.length > MAX_MESSAGE) throw AppError.Validation("Messages are at most $MAX_MESSAGE characters.")
        api.send(userId, text)
    }

    override suspend fun markRead(userId: Int): Outcome<Inbox> = outcomeOf { api.markRead(userId) }

    override suspend fun report(target: ReportTarget, reason: ContentReportReason): Outcome<String> =
        outcomeOf { api.report(target.kind.wire, target.id, reason.wire).message }

    override suspend fun block(userId: Int): Outcome<Unit> = outcomeOf { api.block(userId) }

    private companion object {
        const val MIN_QUERY = 2
        const val MAX_MESSAGE = 1000
    }
}
