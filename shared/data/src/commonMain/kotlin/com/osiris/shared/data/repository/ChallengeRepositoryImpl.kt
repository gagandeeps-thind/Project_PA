package com.osiris.shared.data.repository

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.ChallengeApi
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.model.HubChallenge
import com.osiris.shared.domain.model.HubSection
import com.osiris.shared.domain.model.ReportReason
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.run.LatLng

class ChallengeRepositoryImpl(private val api: ChallengeApi) : ChallengeRepository {
    override suspend fun nearby(position: LatLng, radiusKm: Double): Outcome<List<ChallengeSummary>> =
        outcomeOf { api.nearby(position.lat, position.lng, radiusKm) }

    override suspend fun challenge(id: Int): Outcome<ChallengeSummary> = outcomeOf { api.challenge(id) }

    override suspend fun course(challengeId: Int): Outcome<CourseRoute> = outcomeOf { api.course(challengeId) }

    override suspend fun join(challengeId: Int): Outcome<Unit> = outcomeOf { api.join(challengeId) }

    override suspend fun submitAttempt(challengeId: Int, runId: Int): Outcome<AttemptSummary> =
        outcomeOf { api.submitAttempt(challengeId, runId) }

    override suspend fun hub(section: HubSection): Outcome<List<HubChallenge>> = outcomeOf { api.hub(section.wire).items }

    override suspend fun myCourses(): Outcome<List<CourseSummary>> = outcomeOf { api.myCourses() }

    override suspend fun registerCourse(runId: Int, name: String): Outcome<Unit> = outcomeOf {
        val trimmed = name.trim()
        if (trimmed.length < 3) throw AppError.Validation("Course names need at least 3 characters.")
        api.registerCourse(runId, trimmed)
    }

    override suspend fun publish(draft: ChallengeDraft): Outcome<Int> = outcomeOf {
        draft.validate()?.let { throw AppError.Validation(it) }
        api.publish(draft).id
    }

    override suspend fun invite(challengeId: Int): Outcome<String> = outcomeOf { api.invite(challengeId).shareText }

    override suspend fun report(challengeId: Int, reason: ReportReason): Outcome<String> =
        outcomeOf { api.report("challenge", challengeId, null, reason.wire).message }

    override suspend fun blockCreator(challengeId: Int): Outcome<Unit> = outcomeOf { api.blockCreator(challengeId) }
}
