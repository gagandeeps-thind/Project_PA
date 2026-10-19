package com.osiris.shared.domain.model

import com.osiris.shared.domain.exercise.Verdict
import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Upload state of a set saved on the phone. */
enum class SyncState(val wire: String) {
    PENDING("pending"),
    SYNCED("synced"),
    FAILED("failed");

    companion object {
        fun fromWire(value: String): SyncState = entries.firstOrNull { it.wire == value } ?: PENDING
    }
}

/** A set saved on the phone, waiting to upload or already accepted by the server. */
data class StoredSession(
    val id: String,
    val userId: Int,
    val exerciseKey: String,
    val rulesVersion: String,
    val startedAt: Instant,
    val durationS: Double,
    val repsAttempted: Int,
    val repsValid: Int,
    val holdS: Double,
    val formScore: Double,
    val verdict: Verdict,
    val reasons: List<String>,
    val repDurationsS: List<Double>,
    val syncState: SyncState,
    val serverStatus: String? = null,
    val xpAwarded: Int = 0,
) {
    fun toUpload(): ExerciseUpload = ExerciseUpload(
        clientSessionId = id,
        exerciseKey = exerciseKey,
        rulesVersion = rulesVersion,
        startedAt = startedAt.toString(),
        durationS = durationS,
        repsAttempted = repsAttempted,
        repsValid = repsValid,
        holdS = holdS,
        formScore = formScore,
        clientVerdict = verdict.wire,
        reasonCodes = reasons,
        repDurationsS = repDurationsS,
    )
}

/** Body for `POST /api/v2/exercise-sessions`. Idempotent per [clientSessionId]. */
@Serializable
data class ExerciseUpload(
    @SerialName("client_session_id") val clientSessionId: String,
    @SerialName("exercise_key") val exerciseKey: String,
    @SerialName("rules_version") val rulesVersion: String,
    @SerialName("started_at") val startedAt: String,
    @SerialName("duration_s") val durationS: Double,
    @SerialName("reps_attempted") val repsAttempted: Int,
    @SerialName("reps_valid") val repsValid: Int,
    @SerialName("hold_s") val holdS: Double,
    @SerialName("form_score") val formScore: Double,
    @SerialName("client_verdict") val clientVerdict: String,
    @SerialName("reason_codes") val reasonCodes: List<String>,
    @SerialName("rep_durations_s") val repDurationsS: List<Double>,
)

@Serializable
data class ExerciseUploadResult(
    val status: String,
    @SerialName("xp_awarded") val xpAwarded: Int = 0,
)

@Serializable
data class ServerExerciseSession(
    @SerialName("client_session_id") val clientSessionId: String,
    val status: String,
    @SerialName("xp_awarded") val xpAwarded: Int = 0,
)

@Serializable
data class ExerciseHistoryResponse(val sessions: List<ServerExerciseSession> = emptyList())

@Serializable
data class ConsentState(val granted: Boolean)

/** What happened to a finished set: saved locally, and uploaded if the network allowed. */
data class SetOutcome(val uploaded: Boolean, val xpAwarded: Int)

/** Recent sets and personal bests (most valid reps, or longest hold, per exercise). */
data class ExerciseHistory(val recent: List<StoredSession>, val bests: Map<String, Double>) {
    companion object {
        val EMPTY = ExerciseHistory(emptyList(), emptyMap())
    }
}

/** Result of one upload pass. [offline] when the pass stopped because the network is down. */
data class SyncResult(val uploaded: Int, val xpAwarded: Int, val offline: Boolean = false)
