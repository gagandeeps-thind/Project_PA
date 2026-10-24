package com.osiris.shared.domain.run

import com.osiris.shared.domain.model.RoutePoint
import kotlin.time.Duration
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.DurationUnit
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
    /** When the fix was measured. Null means when it arrived, which adds delivery jitter to segment speeds. */
    val at: Instant? = null,
) {
    val position: LatLng get() = LatLng(lat, lng)
}

/** What is being recorded. [wire] is the API's `activity_type`; rides wait for their own game rules. */
enum class Sport(val wire: String, val label: String) {
    RUN("run", "Run"),
    WALK("walk", "Walk"),
    HIKE("hike", "Hike"),
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
    /** Run-relative time of the last point; the server rejects timestamps that do not increase. */
    @SerialName("last_t_ms") val lastTMs: Long? = null,
    val sport: String = Sport.RUN.wire,
    /** Stops (slower than [MOVING_MIN_MPS] for [AUTO_PAUSE_AFTER_MS] straight) leave moving time. */
    @SerialName("auto_pause") val autoPause: Boolean = true,
    /** Length of the current slow stretch. */
    @SerialName("still_ms") val stillMs: Long = 0,
    @SerialName("paused_ms") val pausedMs: Long = 0,
    @SerialName("elevation_gain_m") val elevationGainM: Double = 0.0,
    /** Lowest altitude since the last counted climb. */
    @SerialName("climb_base_m") val climbBaseM: Double? = null,
) {
    /** Auto-paused right now. Points keep recording: they are the run's evidence. */
    val paused: Boolean get() = autoPause && stillMs >= AUTO_PAUSE_AFTER_MS
    val uploaded: Int get() = nextSequence - pending.size

    fun elapsed(now: Instant): Duration = now - startedAt

    /** Runs left open this long were almost certainly abandoned (app killed, phone died). */
    fun isStale(now: Instant): Boolean = elapsed(now) > STALE_AFTER

    /** Elapsed time minus stops; while paused it holds at the last point. Same rule as the server's figure. */
    fun moving(now: Instant): Duration {
        val upTo = if (paused) (lastTMs ?: 0).milliseconds else elapsed(now)
        return (upTo - pausedMs.milliseconds).coerceAtLeast(Duration.ZERO)
    }

    /** Seconds per kilometre of moving time, once the run is long enough for a meaningful pace. */
    fun paceSecPerKm(now: Instant): Double? =
        if (distanceM > 50) moving(now).inWholeSeconds / (distanceM / 1000) else null

    /**
     * Appends a fix with the next sequence number and adds the segment to the distance. A fix measured
     * before the run started (a cached position) or not after the last point is dropped.
     */
    fun withFix(fix: LocationFix, now: Instant): ActiveRun {
        val tMs = ((fix.at ?: now) - startedAt).inWholeMilliseconds
        if (tMs < 0 || (lastTMs != null && tMs <= lastTMs)) return this
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
        val dtMs = if (lastTMs == null) 0L else tMs - lastTMs
        // Prefer the phone's Doppler speed: position deltas jitter by metres when standing still. But a
        // reported 0 is a stop only if the position stayed within jitter; some phones report 0 while moving.
        val reported = point.speedMps
        val slow = dtMs > 0 && if (reported == null) {
            segment / dtMs.milliseconds.toDouble(DurationUnit.SECONDS) < MOVING_MIN_MPS
        } else {
            reported < MOVING_MIN_MPS && segment <= maxOf(fix.accuracyM ?: 0.0, JITTER_FLOOR_M)
        }
        return copy(
            nextSequence = nextSequence + 1,
            distanceM = distanceM + segment,
            pending = pending + point,
            lastLat = fix.lat,
            lastLng = fix.lng,
            lastTMs = tMs,
        ).stopped(dtMs, slow).climbed(fix.altitudeM)
    }

    private fun stopped(dtMs: Long, slow: Boolean): ActiveRun {
        val still = if (slow) stillMs + dtMs else 0L
        val add = when {
            !autoPause || still < AUTO_PAUSE_AFTER_MS -> 0L
            stillMs < AUTO_PAUSE_AFTER_MS -> still // the pause starts: the whole slow stretch was stopped
            else -> dtMs
        }
        return copy(stillMs = still, pausedMs = pausedMs + add)
    }

    private fun climbed(altitudeM: Double?): ActiveRun {
        val base = climbBaseM
        return when {
            altitudeM == null -> this
            base == null || altitudeM < base -> copy(climbBaseM = altitudeM)
            altitudeM - base >= CLIMB_STEP_M -> copy(elevationGainM = elevationGainM + altitudeM - base, climbBaseM = altitudeM)
            else -> this
        }
    }

    companion object {
        val STALE_AFTER: Duration = 12.hours

        /** Keep in step with run_verifier.py: MOVING_MIN_MPS, AUTO_PAUSE_AFTER_SECONDS, JITTER_FLOOR_M, CLIMB_STEP_M. */
        const val MOVING_MIN_MPS = 0.5
        const val JITTER_FLOOR_M = 5.0
        const val AUTO_PAUSE_AFTER_MS = 10_000L
        const val CLIMB_STEP_M = 3.0
    }
}
