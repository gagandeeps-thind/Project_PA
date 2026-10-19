package com.osiris.shared.domain.exercise

import java.io.File
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/*
 * Builds synthetic BlazePose-like skeletons from joint angles, so engine tests replay genuine and
 * fake movement without a camera. Port of Osiris_customer/test/exercise/pose_synth.dart.
 */

fun loadCatalog(): ExerciseCatalog =
    ExerciseCatalog.parse(File(System.getProperty("osiris.catalog") ?: error("osiris.catalog not set")).readText())

private const val SCALE = 400.0

/** Triangular landmark jitter of up to [px] pixels; same sequence as the Dart tests' `Noise`. */
class Noise(seed: Int, private val px: Double = 1.5) {
    private val r = DartRandom(seed.toLong())
    fun next(): Double = if (px == 0.0) 0.0 else (r.nextDouble() + r.nextDouble() - 1) * px
}

private fun step(x: Double, y: Double, deg: Double, len: Double): Pair<Double, Double> =
    (x + cos(deg * PI / 180) * len * SCALE) to (y + sin(deg * PI / 180) * len * SCALE)

/**
 * Side-view skeleton anchored at the hip. [torsoDeg] is the direction hip → shoulder in image
 * degrees (−90 is straight up, 180 is to the left); every other value is the interior angle at
 * that joint. Pass [thighDeg] instead to fix the thigh and derive the torso (sit-ups).
 */
fun sideChain(
    side: String,
    torsoDeg: Double = -90.0,
    thighDeg: Double? = null,
    hip: Double = 180.0,
    knee: Double = 180.0,
    shoulder: Double = 20.0,
    elbow: Double = 170.0,
    ox: Double = 200.0,
    oy: Double = 250.0,
    likelihood: Double = 0.95,
    noise: Noise? = null,
): Map<String, Landmark> {
    val torso = if (thighDeg == null) torsoDeg else thighDeg - hip
    val thigh = torso + hip
    val shank = thigh + 180 - knee
    val upperArm = torso + 180 + shoulder
    val forearm = upperArm + 180 - elbow
    val pts = linkedMapOf("hip" to (ox to oy))
    pts["shoulder"] = step(ox, oy, torso, 0.30)
    pts["knee"] = step(ox, oy, thigh, 0.25)
    pts["ankle"] = step(pts.getValue("knee").first, pts.getValue("knee").second, shank, 0.25)
    pts["elbow"] = step(pts.getValue("shoulder").first, pts.getValue("shoulder").second, upperArm, 0.17)
    pts["wrist"] = step(pts.getValue("elbow").first, pts.getValue("elbow").second, forearm, 0.15)
    val s = pts.getValue("shoulder")
    val nose = step(s.first, s.second, torso, 0.08)
    val out = linkedMapOf<String, Landmark>()
    for ((k, v) in pts) {
        out["${side}_$k"] = Landmark(v.first + (noise?.next() ?: 0.0), v.second + (noise?.next() ?: 0.0), likelihood)
    }
    out["nose"] = Landmark(nose.first, nose.second, likelihood)
    return out
}

/** Both sides of a side-on body; the far side is slightly offset and less confident. */
fun sideBody(
    torsoDeg: Double = -90.0,
    thighDeg: Double? = null,
    hip: Double = 180.0,
    knee: Double = 180.0,
    shoulder: Double = 20.0,
    elbow: Double = 170.0,
    farKnee: Double? = null,
    farHip: Double? = null,
    nearLikelihood: Double = 0.95,
    farLikelihood: Double = 0.7,
    noise: Noise? = null,
): Map<String, Landmark> =
    sideChain("right", torsoDeg, thighDeg, farHip ?: hip, farKnee ?: knee, shoulder, elbow, ox = 204.0, likelihood = farLikelihood, noise = noise) +
        sideChain("left", torsoDeg, thighDeg, hip, knee, shoulder, elbow, likelihood = nearLikelihood, noise = noise)

/** Front view for jumping jacks: [arm] is the hip-shoulder-wrist angle, [spread] the ankle distance over hip width. */
fun frontBody(arm: Double, spread: Double, noise: Noise? = null): Map<String, Landmark> {
    val cx = 200.0
    val hipY = 300.0
    val shoulderY = 180.0
    val hipHalf = 24.0
    val shoulderHalf = 36.0
    val armLen = 128.0
    fun p(x: Double, y: Double) = Landmark(x + (noise?.next() ?: 0.0), y + (noise?.next() ?: 0.0), 0.95)
    val out = linkedMapOf("nose" to p(cx, shoulderY - 40))
    for (sign in listOf(-1.0, 1.0)) {
        val side = if (sign < 0) "left" else "right"
        val sx = cx + sign * shoulderHalf
        val rad = arm * PI / 180
        // Rotate the downward ray (towards the hip) outwards by `arm` degrees.
        val wx = sx + sign * sin(rad) * armLen
        val wy = shoulderY + cos(rad) * armLen
        val ax = cx + sign * spread * hipHalf
        out["${side}_shoulder"] = p(sx, shoulderY)
        out["${side}_elbow"] = p((sx + wx) / 2, (shoulderY + wy) / 2)
        out["${side}_wrist"] = p(wx, wy)
        out["${side}_hip"] = p(cx + sign * hipHalf, hipY)
        out["${side}_ankle"] = p(ax, hipY + 200)
        out["${side}_knee"] = p((cx + sign * hipHalf + ax) / 2, hipY + 100)
    }
    return out
}

/**
 * Frames for a sequence of movement cycles. [profile] maps phase 0..1 (and the cycle index, −1
 * during the lead-in) to a pose; each cycle lasts the matching entry of [cycleMs]; [pauseMs] of
 * rest follows each cycle.
 */
fun cycles(
    cycleMs: List<Int>,
    fps: Int = 30,
    pauseMs: Int = 300,
    startMs: Long = 0,
    leadInMs: Int = 500,
    profile: (phase: Double, cycle: Int) -> Map<String, Landmark>,
): List<PoseFrame> {
    val frames = mutableListOf<PoseFrame>()
    val step = 1000 / fps
    var t = startMs
    var i = 0
    while (i < leadInMs) {
        frames += PoseFrame(t, profile(0.0, -1)); t += step; i += step
    }
    for (c in cycleMs.indices) {
        val ms = cycleMs[c]
        var e = 0
        while (e < ms) {
            frames += PoseFrame(t, profile(e.toDouble() / ms, c)); t += step; e += step
        }
        e = 0
        while (e < pauseMs) {
            frames += PoseFrame(t, profile(0.0, c)); t += step; e += step
        }
    }
    return frames
}

/** Smooth rest → peak → rest value for phase 0..1. */
fun swing(phase: Double, rest: Double, peak: Double): Double = rest + (peak - rest) * (1 - cos(2 * PI * phase)) / 2

/** Human-like tempo: [n] cycles around [baseMs] with ±15% variation. */
fun humanTempo(n: Int, baseMs: Int, seed: Int = 1): List<Int> {
    val r = DartRandom(seed.toLong())
    // Dart's round() rounds halves away from zero (kotlin.math.round rounds them to even).
    return List(n) { kotlin.math.floor(baseMs * (0.85 + r.nextDouble() * 0.3) + 0.5).toInt() }
}

fun judge(catalog: ExerciseCatalog, key: String, frames: List<PoseFrame>): SessionSummary {
    val engine = RepEngine(catalog.byKey(key)!!, catalog)
    frames.forEach(engine::addFrame)
    return engine.finish()
}
