package com.osiris.shared.domain.run

import kotlin.time.Instant

/**
 * When auto-pause counts the player as stopped: slower than [mps] for [ActiveRun.AUTO_PAUSE_AFTER_MS]
 * straight. The chosen speed is sent with the finish request, so the server's moving time uses the
 * same rule. [OFF] counts every second as moving.
 */
enum class AutoPause(val mps: Double, val label: String) {
    OFF(mps = 0.0, label = "Off"),
    STOPS(mps = ActiveRun.MOVING_MIN_MPS, label = "Stops only"),
    SLOW(mps = 1.0, label = "Under 3.6 km/h"),
    WALKING(mps = 1.5, label = "Under 5.4 km/h"),
    ;

    val on: Boolean get() = this != OFF

    companion object {
        /** The setting a recorded run was started with. */
        fun of(run: ActiveRun): AutoPause =
            if (!run.autoPause) OFF else entries.firstOrNull { it.on && it.mps == run.autoPauseMps } ?: STOPS
    }
}

/** How often audio cues speak: every kilometre, or every few minutes of moving time. */
enum class CueInterval(val label: String, private val metres: Double?, private val seconds: Long?) {
    KILOMETRE("Every km", metres = 1000.0, seconds = null),
    FIVE_MINUTES("Every 5 min", metres = null, seconds = 300),
    TEN_MINUTES("Every 10 min", metres = null, seconds = 600),
    ;

    /** How many cue points the run has passed. A cue is due each time this grows. */
    fun mark(run: ActiveRun, now: Instant): Int = when {
        metres != null -> (run.distanceM / metres).toInt()
        else -> (run.moving(now).inWholeSeconds / requireNotNull(seconds)).toInt()
    }

    /** Minutes of moving time at [mark], for time-based intervals; null for distance. */
    fun minutesAt(mark: Int): Long? = seconds?.let { it * mark / SECONDS_PER_MINUTE }

    private companion object {
        const val SECONDS_PER_MINUTE = 60L
    }
}
