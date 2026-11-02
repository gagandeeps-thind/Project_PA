package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
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

/** Start tab workouts: catalog, results, uploads, posts and history. */
interface TrainingRepository {
    /** The activity catalog; fetched once, then served from memory. */
    suspend fun activities(): Outcome<List<TrainingActivity>>

    /** The motivation quote; a new one once per app launch, never the same twice in a row. */
    suspend fun quote(): Outcome<Quote>

    suspend fun summary(activityKey: String): Outcome<TrainingSummary>

    suspend fun sessions(activityKey: String? = null, offset: Int = 0): Outcome<List<TrainingSession>>

    suspend fun session(id: Int): Outcome<TrainingSession>

    /** Saves a finished session; uploading the same client id again returns the saved one. */
    suspend fun upload(session: NewTrainingSession): Outcome<TrainingSession>

    /** Posts a saved session to the feed; posting twice returns the same post. */
    suspend fun post(sessionId: Int, caption: String): Outcome<FeedPost>

    suspend fun progress(weeks: Int = 8): Outcome<TrainingProgress>

    suspend fun connections(): Outcome<List<Connection>>
}

/** Group challenges among connections, plus official Osiris ones. */
interface GroupChallengeRepository {
    suspend fun all(): Outcome<GroupChallenges>

    suspend fun detail(id: Int): Outcome<GroupChallenge>

    suspend fun create(challenge: NewGroupChallenge): Outcome<GroupChallenge>

    suspend fun join(id: Int): Outcome<GroupChallenge>

    suspend fun leave(id: Int): Outcome<GroupChallenge>
}
