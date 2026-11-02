package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.GroupChallengeApi
import com.osiris.shared.data.network.api.TrainingApi
import com.osiris.shared.domain.model.Connection
import com.osiris.shared.domain.model.FeedPost
import com.osiris.shared.domain.model.GroupChallenge
import com.osiris.shared.domain.model.GroupChallenges
import com.osiris.shared.domain.model.NewGroupChallenge
import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.Quote
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingProgress
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.model.TrainingSummary
import com.osiris.shared.domain.repository.GroupChallengeRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.russhwolf.settings.Settings

class TrainingRepositoryImpl(private val api: TrainingApi, private val settings: Settings) : TrainingRepository {
    private var activities: List<TrainingActivity>? = null

    // One quote per process: the board shows something new each time the app opens.
    private var quote: Quote? = null

    override suspend fun activities(): Outcome<List<TrainingActivity>> =
        outcomeOf { activities ?: api.activities().also { activities = it } }

    override suspend fun quote(): Outcome<Quote> = outcomeOf {
        quote ?: api.quote(exclude = settings.getIntOrNull(KEY_LAST_QUOTE)).also {
            quote = it
            settings.putInt(KEY_LAST_QUOTE, it.id)
        }
    }

    override suspend fun summary(activityKey: String): Outcome<TrainingSummary> = outcomeOf { api.summary(activityKey) }

    override suspend fun sessions(activityKey: String?, offset: Int): Outcome<List<TrainingSession>> =
        outcomeOf { api.sessions(activityKey, offset).items }

    override suspend fun session(id: Int): Outcome<TrainingSession> = outcomeOf { api.session(id) }

    override suspend fun upload(session: NewTrainingSession): Outcome<TrainingSession> = outcomeOf { api.upload(session) }

    override suspend fun post(sessionId: Int, caption: String): Outcome<FeedPost> = outcomeOf { api.post(sessionId, caption) }

    override suspend fun progress(weeks: Int): Outcome<TrainingProgress> = outcomeOf { api.progress(weeks) }

    override suspend fun connections(): Outcome<List<Connection>> = outcomeOf { api.connections() }

    private companion object {
        const val KEY_LAST_QUOTE = "osiris.last_quote.v1"
    }
}

class GroupChallengeRepositoryImpl(private val api: GroupChallengeApi) : GroupChallengeRepository {
    override suspend fun all(): Outcome<GroupChallenges> = outcomeOf { api.all() }

    override suspend fun detail(id: Int): Outcome<GroupChallenge> = outcomeOf { api.detail(id) }

    override suspend fun create(challenge: NewGroupChallenge): Outcome<GroupChallenge> = outcomeOf { api.create(challenge) }

    override suspend fun join(id: Int): Outcome<GroupChallenge> = outcomeOf { api.join(id) }

    override suspend fun leave(id: Int): Outcome<GroupChallenge> = outcomeOf { api.leave(id) }
}
