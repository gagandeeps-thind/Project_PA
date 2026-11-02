package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
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
import com.osiris.shared.domain.model.TrainingSessions
import com.osiris.shared.domain.model.TrainingSummary

/** Start tab: training sessions, results, quotes and connections. */
class TrainingApi(private val api: ApiClient) {
    suspend fun activities(): List<TrainingActivity> = api.get("/api/v2/training/activities")

    suspend fun quote(exclude: Int?): Quote = api.get("/api/v2/motivation/quote", mapOf("exclude" to exclude))

    suspend fun summary(activity: String): TrainingSummary = api.get("/api/v2/me/training/summary", mapOf("activity" to activity))

    suspend fun sessions(activity: String?, offset: Int): TrainingSessions =
        api.get("/api/v2/me/training/sessions", mapOf("activity" to activity, "offset" to offset))

    suspend fun session(id: Int): TrainingSession = api.get("/api/v2/me/training/sessions/$id")

    suspend fun upload(session: NewTrainingSession): TrainingSession = api.postBody("/api/v2/training/sessions", session)

    suspend fun post(id: Int, caption: String): FeedPost =
        api.post("/api/v2/training/sessions/$id/post", ApiClient.body("caption" to caption))

    suspend fun progress(weeks: Int): TrainingProgress = api.get("/api/v2/me/training/progress", mapOf("weeks" to weeks))

    suspend fun connections(): List<Connection> = api.get("/api/v2/me/connections")
}

/** Start tab: group challenges. */
class GroupChallengeApi(private val api: ApiClient) {
    suspend fun all(): GroupChallenges = api.get("/api/v2/group-challenges")

    suspend fun detail(id: Int): GroupChallenge = api.get("/api/v2/group-challenges/$id")

    suspend fun create(challenge: NewGroupChallenge): GroupChallenge = api.postBody("/api/v2/group-challenges", challenge)

    suspend fun join(id: Int): GroupChallenge = api.post("/api/v2/group-challenges/$id/join")

    suspend fun leave(id: Int): GroupChallenge = api.post("/api/v2/group-challenges/$id/leave")

    suspend fun cancel(id: Int): GroupChallenge = api.post("/api/v2/group-challenges/$id/cancel")
}
