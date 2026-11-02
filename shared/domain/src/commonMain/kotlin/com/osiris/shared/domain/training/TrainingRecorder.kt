package com.osiris.shared.domain.training

import com.osiris.shared.domain.model.TrainingSeries
import com.osiris.shared.domain.run.Geo
import com.osiris.shared.domain.run.LocationFix
import kotlin.time.Instant

/** A telemetry stream of a live session. [wire] is its key in the upload. */
enum class Channel(val wire: String, val label: String, val unit: String) {
    HR("hr", "Heart rate", "bpm"),
    POWER("power", "Power", "W"),
    SPEED("speed", "Speed", "km/h"),
    ELEVATION("elevation", "Elevation", "m"),
}

/**
 * Records one live session: at most one sample per channel per second, paused time left out,
 * distance from GPS (or, with no GPS, from sensor speed), and the series downsampled for upload.
 */
class TrainingRecorder(private val startedAt: Instant) {
    private val points = Channel.entries.associateWith { mutableListOf<List<Double>>() }
    private var pausedTotalMs = 0L
    private var pausedAt: Instant? = null
    private var lastFix: LocationFix? = null
    private var gpsDistanceM = 0.0
    private var sensorDistanceM = 0.0
    private var hasGps = false
    private var lastSensorSpeed: Pair<Double, Double>? = null   // (elapsed s, m/s)

    val paused: Boolean get() = pausedAt != null

    /** Metres so far: GPS when there were fixes, otherwise integrated sensor speed. */
    val distanceM: Double get() = if (hasGps) gpsDistanceM else sensorDistanceM

    fun elapsedS(at: Instant): Double {
        val pausedNow = pausedAt?.let { (at - it).inWholeMilliseconds } ?: 0L
        return ((at - startedAt).inWholeMilliseconds - pausedTotalMs - pausedNow).coerceAtLeast(0) / MS
    }

    fun pause(at: Instant) {
        if (pausedAt == null) pausedAt = at
    }

    fun resume(at: Instant) {
        val since = pausedAt ?: return
        pausedTotalMs += (at - since).inWholeMilliseconds
        pausedAt = null
        // The first fix after a pause starts a new leg; the gap is not distance covered.
        lastFix = null
        lastSensorSpeed = null
    }

    /** A sensor sample. Sensor speed also wins over GPS speed for [SENSOR_SPEED_FRESH_S]. */
    fun add(channel: Channel, value: Double, at: Instant) {
        if (paused) return
        val t = elapsedS(at)
        if (channel == Channel.SPEED) {
            lastSensorSpeed?.let { (prevT, prevV) ->
                val dt = t - prevT
                if (dt in 0.0..SENSOR_GAP_S) sensorDistanceM += (prevV + value) / 2 * dt
            }
            lastSensorSpeed = t to value
        }
        record(channel, value, t)
    }

    fun addFix(fix: LocationFix, at: Instant) {
        if (paused) return
        if ((fix.accuracyM ?: 0.0) > MAX_ACCURACY_M) return
        val t = elapsedS(at)
        hasGps = true
        lastFix?.let { gpsDistanceM += Geo.distanceM(it.position, fix.position) }
        lastFix = fix
        val sensorFresh = lastSensorSpeed?.let { t - it.first <= SENSOR_SPEED_FRESH_S } == true
        fix.speedMps?.takeIf { it >= 0 && !sensorFresh }?.let { record(Channel.SPEED, it, t) }
        fix.altitudeM?.let { record(Channel.ELEVATION, it, t) }
    }

    fun latest(channel: Channel): Double? = points.getValue(channel).lastOrNull()?.get(1)

    /** Every channel, each capped at [maxPoints] by averaging neighbouring points. */
    fun series(maxPoints: Int = MAX_POINTS): TrainingSeries {
        fun of(c: Channel) = downsample(points.getValue(c), maxPoints)
        return TrainingSeries(hr = of(Channel.HR), power = of(Channel.POWER), speed = of(Channel.SPEED),
            elevation = of(Channel.ELEVATION))
    }

    private fun record(channel: Channel, value: Double, t: Double) {
        val list = points.getValue(channel)
        val last = list.lastOrNull()
        if (last != null && t - last[0] < MIN_GAP_S) return
        list += listOf(t, value)
    }

    companion object {
        const val MAX_POINTS = 720
        private const val MS = 1000.0
        private const val MIN_GAP_S = 1.0
        private const val MAX_ACCURACY_M = 50.0
        private const val SENSOR_SPEED_FRESH_S = 5.0
        private const val SENSOR_GAP_S = 10.0

        fun downsample(points: List<List<Double>>, maxPoints: Int): List<List<Double>> {
            val n = points.size
            if (n <= maxPoints) return points.toList()
            // Even split into exactly maxPoints buckets; each is non-empty because n > maxPoints.
            return List(maxPoints) { i -> points.subList(i * n / maxPoints, (i + 1) * n / maxPoints) }
                .map { c -> listOf(c.sumOf { it[0] } / c.size, c.sumOf { it[1] } / c.size) }
        }
    }
}
