package com.osiris.shared.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** `POST /api/v2/runs`, `GET /api/v2/runs/{id}`. */
@Serializable
data class RunRecord(
    val id: Int,
    @SerialName("point_count") val pointCount: Int = 0,
    @SerialName("verification_status") val verificationStatus: String? = null,
)

/** One GPS fix queued for upload. [sequence] is contiguous per run, assigned at capture time. */
@Serializable
data class RoutePoint(
    val sequence: Int,
    @SerialName("t_ms") val tMs: Long,
    val lat: Double,
    val lng: Double,
    @SerialName("accuracy_m") val accuracyM: Double? = null,
    @SerialName("speed_mps") val speedMps: Double? = null,
    @SerialName("altitude_m") val altitudeM: Double? = null,
)

/** `POST /api/v2/runs/{id}/finish`. */
@Serializable
data class RunResult(
    @SerialName("verification_status") val verificationStatus: String? = null,
    @SerialName("rejection_reason") val rejectionReason: String? = null,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    @SerialName("duration_seconds") val durationSeconds: Double = 0.0,
    @SerialName("moving_seconds") val movingSeconds: Double? = null,
    @SerialName("elevation_gain_m") val elevationGainM: Double? = null,
    @SerialName("xp_awarded") val xpAwarded: Int = 0,
) {
    val accepted: Boolean get() = verificationStatus == "accepted"
    val reasons: List<String> get() = ReasonCopy.explainAll(rejectionReason)
}
