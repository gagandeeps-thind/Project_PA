package com.osiris.shared.domain.exercise

/**
 * Pose frames per second over a sliding window of the most recent frame times.
 *
 * The window also skips model warm-up: the first ML Kit frame can take seconds, and that gap
 * leaves the window after [window] frames.
 */
class FrameRateMeter(private val window: Int = 15) {
    private val times = ArrayDeque<Long>()

    fun add(tMs: Long) {
        times.addLast(tMs)
        while (times.size > window) times.removeFirst()
    }

    /** Null until the window is full. */
    val fps: Double?
        get() {
            if (times.size < window) return null
            val span = times.last() - times.first()
            return if (span <= 0) null else (times.size - 1) * 1000.0 / span
        }
}

/**
 * Whether pose tracking is too slow for an exercise, with hysteresis so the warning does not
 * flicker when the rate hovers at the limit: on below [minFps], off again at 20% above it.
 */
class SlowTrackingDetector(private val minFps: Double) {
    private var slow = false

    fun update(fps: Double?): Boolean {
        if (fps == null) return slow
        if (!slow && fps < minFps) slow = true
        if (slow && fps >= minFps * 1.2) slow = false
        return slow
    }
}

/** Inference timing for the on-device performance read-out. */
class PoseStats {
    var processed = 0
        private set
    var dropped = 0
        private set
    private var totalInferenceUs = 0L
    var maxInferenceUs = 0L
        private set
    private var firstMs: Long? = null
    private var lastMs = 0L

    fun record(tMs: Long, inferenceUs: Long) {
        if (firstMs == null) firstMs = tMs
        lastMs = tMs
        processed++
        totalInferenceUs += inferenceUs
        if (inferenceUs > maxInferenceUs) maxInferenceUs = inferenceUs
    }

    /** A frame skipped because inference was still busy with the previous one. */
    fun drop() {
        dropped++
    }

    val avgInferenceMs: Double get() = if (processed == 0) 0.0 else totalInferenceUs.toDouble() / processed / 1000

    val fps: Double
        get() {
            val first = firstMs ?: return 0.0
            if (lastMs <= first) return 0.0
            return (processed - 1) * 1000.0 / (lastMs - first)
        }

    override fun toString(): String =
        "${fps.format1()} fps · ${avgInferenceMs.format1()} ms avg / ${(maxInferenceUs / 1000.0).format1()} ms max · $dropped dropped"
}

private fun Double.format1(): String = roundHalfUp(this, 1).toString()
