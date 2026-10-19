package com.osiris.shared.domain.model

import com.osiris.shared.core.util.newHexId
import com.osiris.shared.domain.run.LatLng
import kotlin.time.Duration
import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** A player's attempt at a challenge. */
@Serializable
data class AttemptSummary(
    val id: Int,
    @SerialName("challenge_id") val challengeId: Int,
    val status: String,
    val outcome: String? = null,
    @SerialName("run_id") val runId: Int? = null,
    @SerialName("elapsed_seconds") val elapsedSeconds: Double? = null,
    @SerialName("target_seconds") val targetSeconds: Double = 0.0,
    @SerialName("course_coverage") val courseCoverage: Double? = null,
    @SerialName("reason_codes") val reasonCodes: List<String> = emptyList(),
    @SerialName("xp_awarded") val xpAwarded: Int = 0,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("joined_at") val joinedAt: Instant? = null,
) {
    /** Short status label for chips and lists. */
    val label: String
        get() = when (outcome) {
            "won" -> "Won"
            "lost" -> "Completed"
            "voided" -> "Voided"
            else -> when (status) {
                "joined" -> "Joined"
                "review_required" -> "In review"
                "rejected" -> "Not counted"
                else -> status
            }
        }

    /** Heading for the result dialog after a challenge run. */
    val resultTitle: String
        get() = when (outcome) {
            "won" -> "Challenge won!"
            "lost" -> "Challenge completed"
            else -> if (status == "review_required") "Result in review" else "Run not counted"
        }

    /** Whether the player may (re)run the course: joined, or the last run was not counted. */
    val canRun: Boolean get() = status == "joined" || status == "rejected"
}

@Serializable
data class ChallengeSummary(
    val id: Int,
    val title: String,
    val status: String,
    @SerialName("course_distance_m") val courseDistanceM: Double = 0.0,
    @SerialName("target_seconds") val targetSeconds: Double = 0.0,
    @SerialName("entry_crystals") val entryCrystals: Int = 0,
    @SerialName("reward_policy") val rewardPolicy: String = "xp_badge",
    @SerialName("win_xp") val winXp: Int = 0,
    @SerialName("participation_xp") val participationXp: Int = 0,
    @SerialName("safety_notes") val safetyNotes: String? = null,
    @Serializable(with = ServerInstantSerializer::class)
    @SerialName("closes_at") val closesAt: Instant? = null,
    @SerialName("marker_lat") val markerLat: Double = 0.0,
    @SerialName("marker_lng") val markerLng: Double = 0.0,
    @SerialName("distance_km") val distanceKm: Double? = null,
    @SerialName("attempt_count") val attemptCount: Int = 0,
    @SerialName("is_mine") val isMine: Boolean = false,
    @SerialName("my_attempt") val myAttempt: AttemptSummary? = null,
    @SerialName("terms_hash") val termsHash: String = "",
) {
    val marker: LatLng get() = LatLng(markerLat, markerLng)
    val isOpen: Boolean get() = status == "open"
    val canRun: Boolean get() = isOpen && myAttempt?.canRun == true
    val canJoin: Boolean get() = isOpen && !isMine && myAttempt == null

    /** `2d 3h left`, `4h 10m left`, `25m left` or `closed`. */
    fun closesIn(now: Instant): String {
        val closes = closesAt ?: return "closed"
        val d: Duration = closes - now
        if (d.isNegative()) return "closed"
        val days = d.inWholeDays
        val hours = d.inWholeHours
        val minutes = d.inWholeMinutes
        return when {
            days >= 1 -> "${days}d ${hours % 24}h left"
            hours >= 1 -> "${hours}h ${minutes % 60}m left"
            else -> "${minutes}m left"
        }
    }
}

@Serializable
data class CourseSummary(
    val id: Int,
    val name: String,
    val status: String,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("benchmark_seconds") val benchmarkSeconds: Double = 0.0,
    @SerialName("is_loop") val isLoop: Boolean = false,
    @Serializable(with = RouteSerializer::class)
    val route: List<LatLng> = emptyList(),
    @SerialName("open_challenge_id") val openChallengeId: Int? = null,
)

/** `GET /api/v2/challenges/{id}/course`: visible once the player joined. */
@Serializable
data class CourseRoute(
    @Serializable(with = RouteSerializer::class)
    val route: List<LatLng> = emptyList(),
    @SerialName("start_radius_m") val startRadiusM: Double = 0.0,
)

/**
 * Input for publishing a challenge on one of the player's courses. [idempotencyKey] is fixed when
 * the draft is created, so a retry after a lost response never publishes twice.
 */
data class ChallengeDraft(
    val courseId: Int,
    val title: String,
    val windowHours: Int,
    val safetyNotes: String? = null,
    val idempotencyKey: String = "publish-" + newHexId(),
) {
    fun validate(): String? = when {
        title.trim().length < 3 -> "Titles need at least 3 characters."
        windowHours !in 1..(24 * 14) -> "Choose a window between 1 hour and 14 days."
        else -> null
    }
}

/** Human-readable copy for server reason codes. Unknown codes fall back to the code. */
object ReasonCopy {
    private val copy = mapOf(
        "RUN_NOT_ACCEPTED" to "The run did not pass route verification.",
        "START_OUTSIDE_COURSE" to "The run never reached the course start.",
        "FINISH_OUTSIDE_COURSE" to "The run did not reach the course finish.",
        "DISTANCE_MISMATCH" to "The distance run on course differs too much from the course.",
        "ROUTE_OFF_COURSE" to "Too much of the run was off the course route.",
        "CLOCK_SKEW" to "Device timestamps did not match server time.",
        "REVIEW_REQUIRED" to "This result is exceptionally fast, so a reviewer will confirm it.",
        "REVIEW_REJECTED" to "A reviewer rejected this result.",
        "INSUFFICIENT_ROUTE_POINTS" to "Not enough GPS points were recorded.",
        "IMPOSSIBLE_SPEED" to "GPS showed a speed no runner can reach.",
        "ROUTE_GAP_TOO_LARGE" to "GPS dropped out for too long.",
        "DURATION_TOO_SHORT" to "The run was too short.",
        "DISTANCE_TOO_SHORT" to "The run covered too little distance.",
        "GPS_ACCURACY_TOO_LOW" to "GPS accuracy was too low.",
        "NON_MONOTONIC_TIMESTAMPS" to "GPS timestamps were out of order.",
    )

    fun explain(code: String): String = copy[code] ?: code

    /** The server sends run rejections as one comma-separated string. */
    fun explainAll(commaSeparated: String?): List<String> =
        commaSeparated.orEmpty().split(',').map(String::trim).filter(String::isNotEmpty).map(::explain)
}
