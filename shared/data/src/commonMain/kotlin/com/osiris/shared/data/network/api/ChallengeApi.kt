package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.model.InviteLink
import com.osiris.shared.domain.model.MessageResponse
import io.ktor.http.HttpMethod
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/** Courses, challenges and the safety actions on them. */
class ChallengeApi(private val api: ApiClient) {
    @Serializable
    data class Created(val id: Int)

    suspend fun nearby(lat: Double, lng: Double, radiusKm: Double): List<ChallengeSummary> =
        api.get("/api/v2/challenges/nearby", mapOf("lat" to lat, "lng" to lng, "radius_km" to radiusKm))

    suspend fun challenge(id: Int): ChallengeSummary = api.get("/api/v2/challenges/$id")

    suspend fun course(challengeId: Int): CourseRoute = api.get("/api/v2/challenges/$challengeId/course")

    suspend fun join(challengeId: Int) = api.execute(HttpMethod.Post, "/api/v2/challenges/$challengeId/join")

    suspend fun submitAttempt(challengeId: Int, runId: Int): AttemptSummary =
        api.post("/api/v2/challenges/$challengeId/attempts", ApiClient.body("run_id" to runId))

    suspend fun myCourses(): List<CourseSummary> = api.get("/api/v2/courses")

    suspend fun registerCourse(runId: Int, name: String) {
        api.post<JsonObject>("/api/v2/courses", ApiClient.body("run_id" to runId, "name" to name))
    }

    suspend fun publish(d: ChallengeDraft): Created =
        api.post(
            "/api/v2/challenges",
            ApiClient.body(
                "course_id" to d.courseId,
                "title" to d.title.trim(),
                "window_hours" to d.windowHours,
                "safety_notes" to d.safetyNotes?.trim()?.takeIf { it.isNotEmpty() },
                "idempotency_key" to d.idempotencyKey,
            ),
        )

    suspend fun invite(challengeId: Int): InviteLink = api.post("/api/v2/challenges/$challengeId/invites")

    suspend fun report(targetType: String, targetId: Int?, targetRef: String?, reason: String): MessageResponse =
        api.post(
            "/api/v2/reports",
            ApiClient.body("target_type" to targetType, "target_id" to targetId, "target_ref" to targetRef, "reason" to reason),
        )

    suspend fun blockCreator(challengeId: Int) =
        api.execute(HttpMethod.Post, "/api/v2/blocks", ApiClient.body("challenge_id" to challengeId))
}
