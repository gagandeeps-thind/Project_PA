package com.osiris.shared.domain.run

import com.osiris.shared.domain.model.RoutePoint
import kotlin.time.Duration
import kotlin.time.Duration.Companion.hours
import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One position from the platform location service. */
data class LocationFix(
    val lat: Double,
    val lng: Double,
    val accuracyM: Double? = null,
    /** Negative or null when the platform has no speed. */
    val speedMps: Double? = null,
    val altitudeM: Double? = null,
    /**
     * How old the fix already was when it reached the app (platform fix time vs. now). Delivery is
     * batched and jittery, so stamping points on arrival can turn a jog into an impossible speed.
     */
    val ageMs: Long = 0,
) {
    val position: LatLng get() = LatLng(lat, lng)
}

/** The run being recorded, persisted so a restart or an outage never loses route points. */
@Serializable
data class ActiveRun(
    @SerialName("run_id") val runId: Int,
    /** The account that recorded the run. */
    @SerialName("user_id") val userId: Int? = null,
    @SerialName("started_at") val startedAt: Instant,
    @SerialName("challenge_id") val challengeId: Int? = null,
    @SerialName("next_sequence") val nextSequence: Int = 0,
    @SerialName("distance_m") val distanceM: Double = 0.0,
    val pending: List<RoutePoint> = emptyList(),
    /** Last fix, to measure the next segment; kept so distance continues after a restart. */
    @SerialName("last_lat") val lastLat: Double? = null,
    @SerialName("last_lng") val lastLng: Double? = null,
    /** Time of the last point, to keep timestamps strictly increasing. */
    @SerialName("last_t_ms") val lastTMs: Long? = null,
) {
    val uploaded: Int get() = nextSequence - pending.size

    fun elapsed(now: Instant): Duration = now - startedAt

    /** Runs left open this long were almost certainly abandoned (app killed, phone died). */
    fun isStale(now: Instant): Boolean = elapsed(now) > STALE_AFTER

    /** Seconds per kilometre, once the run is long enough for a meaningful pace. */
    fun paceSecPerKm(now: Instant): Double? =
        if (distanceM > 50) elapsed(now).inWholeSeconds / (distanceM / 1000) else null

    /**
     * Appends a fix with the next sequence number and adds the segment to the distance. The point is
     * timed when the fix was taken, not when it arrived; fixes taken before the run started (a cached
     * last position) are ignored.
     */
    fun withFix(fix: LocationFix, now: Instant): ActiveRun {
        val takenMs = (now - startedAt).inWholeMilliseconds - fix.ageMs.coerceAtLeast(0)
        if (takenMs < 0) return this
        val tMs = if (lastTMs == null) takenMs else maxOf(takenMs, lastTMs + 1)
        val last = if (lastLat != null && lastLng != null) LatLng(lastLat, lastLng) else null
        val segment = if (last == null) 0.0 else Geo.distanceM(last, fix.position)
        val point = RoutePoint(
            sequence = nextSequence,
            tMs = tMs,
            lat = fix.lat,
            lng = fix.lng,
            accuracyM = fix.accuracyM,
            speedMps = fix.speedMps?.takeIf { it >= 0 },
            altitudeM = fix.altitudeM,
        )
        return copy(
            nextSequence = nextSequence + 1,
            distanceM = distanceM + segment,
            pending = pending + point,
            lastLat = fix.lat,
            lastLng = fix.lng,
            lastTMs = tMs,
        )
    }

    companion object {
        val STALE_AFTER: Duration = 12.hours
    }
}
