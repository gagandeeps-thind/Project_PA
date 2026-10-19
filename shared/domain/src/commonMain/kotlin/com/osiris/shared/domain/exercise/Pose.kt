package com.osiris.shared.domain.exercise

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.atan2
import kotlin.math.abs
import kotlin.math.sqrt

/** One body landmark in image pixels with the detector's confidence (0..1). */
data class Landmark(val x: Double, val y: Double, val likelihood: Double) {
    fun distanceTo(o: Landmark): Double = sqrt((x - o.x) * (x - o.x) + (y - o.y) * (y - o.y))
}

/**
 * One camera frame's pose. [tMs] is a monotonic timestamp in milliseconds. Landmarks are named
 * like the catalog joints with a side prefix (`left_knee`); `nose` has none. Kept independent of
 * ML Kit and Apple Vision types so the engine runs in plain tests on every platform.
 */
data class PoseFrame(val tMs: Long, val landmarks: Map<String, Landmark>) {
    fun get(side: String, joint: String): Landmark? = landmarks[if (joint == NOSE) NOSE else "${side}_$joint"]

    companion object {
        const val NOSE = "nose"

        /** The joints the rep engine reads; each except [NOSE] exists as `left_` and `right_`. */
        val JOINTS = listOf(NOSE, "shoulder", "elbow", "wrist", "hip", "knee", "ankle")
    }
}

/** Angle at [b] between rays b→a and b→c, in degrees (0..180). */
fun angleDeg(a: Landmark, b: Landmark, c: Landmark): Double {
    val v1x = a.x - b.x
    val v1y = a.y - b.y
    val v2x = c.x - b.x
    val v2y = c.y - b.y
    val n = sqrt(v1x * v1x + v1y * v1y) * sqrt(v2x * v2x + v2y * v2y)
    if (n == 0.0) return 0.0
    val cos = ((v1x * v2x + v1y * v2y) / n).coerceIn(-1.0, 1.0)
    return acos(cos) * 180 / PI
}

/** Tilt of the segment a→b away from the image's horizontal axis, in degrees (0..90). */
fun tiltFromHorizontalDeg(a: Landmark, b: Landmark): Double {
    val dx = abs(b.x - a.x)
    val dy = abs(b.y - a.y)
    if (dx == 0.0 && dy == 0.0) return 0.0
    return atan2(dy, dx) * 180 / PI
}
