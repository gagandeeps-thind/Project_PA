package com.osiris.shared.domain.exercise

import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToLong
import kotlin.math.sqrt

/** Where the player is in the current rep. */
enum class RepPhase { WAITING, REST, MOVING, HOLDING }

/** One completed (or abandoned) rep. [reason] is a rep-level reason code when not [valid]. */
data class RepResult(
    val index: Int,
    val startMs: Long,
    val durationMs: Long,
    val peakValue: Double,
    val valid: Boolean,
    val reason: String? = null,
)

/** Live state for the camera screen, produced per frame. */
data class EngineUpdate(
    val validReps: Int,
    val attemptedReps: Int,
    val holdS: Double,
    val phase: RepPhase,
    val metric: Double?,
    val visible: Boolean,
    val hint: String,
    val newRep: RepResult? = null,
)

/** The device's verdict on one set; uploaded to `POST /api/v2/exercise-sessions`. */
data class SessionSummary(
    val exerciseKey: String,
    val rulesVersion: String,
    val durationS: Double,
    val repsAttempted: Int,
    val repsValid: Int,
    val holdS: Double,
    val formScore: Double,
    val verdict: Verdict,
    val reasons: List<String>,
    val reps: List<RepResult>,
) {
    val validRepDurationsS: List<Double> get() = reps.filter { it.valid }.map { it.durationMs / 1000.0 }
}

/** Outcome of a set, as the device and the server re-check both call it. */
enum class Verdict(val wire: String) {
    VERIFIED("verified"),
    REVIEW("review"),
    REJECTED("rejected");

    companion object {
        fun fromWire(value: String): Verdict = entries.firstOrNull { it.wire == value } ?: REJECTED
    }
}

/** Reason codes the engine can attach. Rep-level codes describe single reps, not the set. */
object ReasonCodes {
    const val TOO_FAST = "too_fast"
    const val TOO_SLOW = "too_slow"
    const val FORM_BREAK = "form_break"
    const val WRONG_POSITION = "wrong_position"
    const val LOW_VISIBILITY = "low_visibility"
    const val TRACKING_GLITCH = "tracking_glitch"
    const val PARTIAL_RANGE = "partial_range"
    const val UNSTEADY_TRACKING = "unsteady_tracking"
    const val NO_VALID_REPS = "no_valid_reps"
    const val LOW_VALID_RATIO = "low_valid_ratio"
    const val REPLAY_SUSPECTED = "replay_suspected"
    const val RATE_IMPLAUSIBLE = "rate_implausible"
    const val NO_ENTRY_TRANSITION = "no_entry_transition"
    const val HOLD_TOO_SHORT = "hold_too_short"
    const val STATIC_POSE = "static_pose"

    /** Evidence on rejected reps; not a session failure on its own. */
    val REP_LEVEL: Set<String> = setOf(
        TOO_FAST, TOO_SLOW, FORM_BREAK, WRONG_POSITION, LOW_VISIBILITY, TRACKING_GLITCH, PARTIAL_RANGE, UNSTEADY_TRACKING,
    )
}

/**
 * Counts reps (or a timed hold) from a stream of poses and judges whether they are genuine.
 *
 * Per frame: the tracked joint angle is computed from the side the camera sees best, lightly
 * smoothed, and run through a rest → moving → rest state machine. A rep counts only if it
 * reached the peak zone, took a humanly possible time, kept form, stayed visible, and its limb
 * lengths stayed stable (a tracker that jumps between people or glitches changes them). At the
 * end, session rules shared with the server flag machine-regular timing (a replayed video),
 * implausible rates and low valid ratios. Cost is O(1) per frame.
 *
 * Port of `Osiris_customer/lib/exercise/rep_engine.dart`; the Kotlin tests replay the same
 * synthetic sets and recordings, so both engines must agree rep for rep.
 */
class RepEngine(val spec: ExerciseSpec, val catalog: ExerciseCatalog) {

    private companion object {
        // Smoothing is a time constant, not a per-frame weight, so a 5 fps phone and a 30 fps
        // phone see the same lag (a per-frame weight averaged the peak away at low frame rates).
        const val SMOOTHING_TAU_MS = 45.0
        // Faster than any human joint: a single-frame jump this large is a tracking glitch...
        const val MAX_DEG_PER_SECOND = 1000.0
        // ...and only when the jump is large in absolute terms: landmark jitter divided by a short
        // frame interval is also "fast", but it never moves a joint angle this far in one frame.
        const val MIN_GLITCH_JUMP_DEG = 60.0
        const val MAX_INVISIBLE_FRACTION = 0.3
        const val MAX_FORM_BREAK_FRACTION = 0.2
        const val MAX_BONE_CV = 0.3
        // Below this landmark spread (in torso lengths) the pose is frozen: injected or a still image.
        const val MIN_LIVENESS_STD = 0.001
        // Out-of-zone wobble shorter than this does not end a hold.
        const val HOLD_GRACE_MS = 600L
        // Tracking noise: variation of the tracked limbs' lengths while the player is still at the
        // top of a rep. Joint-angle noise is about 57.3 degrees x that coefficient of variation;
        // telling a full rep from one stopping 15 degrees short at 3 sigma needs <= 5 degrees,
        // i.e. CV <= 0.087. 0.08 leaves margin.
        const val MAX_REST_LIMB_CV = 0.08
        const val MIN_REST_SAMPLES = 15
        const val LEFT = "left"
        const val RIGHT = "right"
    }

    private var phase = RepPhase.WAITING
    private var side: String? = null
    private var smoothed: Double? = null
    private val restLimbs = mapOf(LEFT to (RunningStats() to RunningStats()), RIGHT to (RunningStats() to RunningStats()))
    // Previous smoothed value and its time, to interpolate when the angle crossed a zone edge.
    private var prevV: Double? = null
    private var prevMs: Long? = null
    private var lastRaw: Double? = null
    private var lastRawMs: Long? = null
    private var firstMs: Long? = null
    private var lastMs = 0L

    // Current rep accumulators.
    private var repStartMs = 0L
    private var reachedPeak = false
    private var peakValue = 0.0
    private var repFrames = 0
    private var repInvisible = 0
    private var repFormBreaks = 0
    private var repWrongPosition = 0
    private var repGlitches = 0
    private val peakSpreads = mutableListOf<Double>()
    private val bone1 = RunningStats()
    private val bone2 = RunningStats()

    private val repList = mutableListOf<RepResult>()
    private var valid = 0
    private var visibleFrames = 0
    private var frames = 0

    // Hold state.
    private var sawRest = false
    private var enteredWithoutRest = false
    private var everHeld = false
    private var holdMs = 0L
    private var holdLastInMs: Long? = null
    private val holdHipX = RunningStats()
    private val holdHipY = RunningStats()

    private var hint = ""

    val reps: List<RepResult> get() = repList.toList()

    fun addFrame(frame: PoseFrame): EngineUpdate {
        if (firstMs == null) firstMs = frame.tMs
        frames++
        lastMs = frame.tMs
        val raw = metric(frame)
        var newRep: RepResult? = null

        if (raw == null) {
            hint = "Move so your whole body is in view"
            if (phase == RepPhase.MOVING) {
                repFrames++
                repInvisible++
            }
            return update(null, false, null)
        }
        visibleFrames++

        val lr = lastRaw
        val lrMs = lastRawMs
        if (lr != null && lrMs != null && frame.tMs > lrMs) {
            val jump = kotlin.math.abs(raw - lr)
            val speed = jump / ((frame.tMs - lrMs) / 1000.0)
            if (jump >= MIN_GLITCH_JUMP_DEG && speed > MAX_DEG_PER_SECOND && phase == RepPhase.MOVING) repGlitches++
        }
        val dtMs = if (lrMs == null) 0L else frame.tMs - lrMs
        lastRaw = raw
        lastRawMs = frame.tMs
        val alpha = 1 - exp(-max(dtMs, 0L) / SMOOTHING_TAU_MS)
        val s = smoothed
        val v = if (s == null) raw else s + alpha * (raw - s)
        smoothed = v

        if (spec.isHold) {
            hold(frame, v)
            return update(v, true, null)
        }

        when (phase) {
            RepPhase.WAITING -> {
                hint = "Get into the start position"
                if (spec.rest.contains(v)) phase = RepPhase.REST
            }
            RepPhase.REST -> {
                sampleRestLimbs(frame)
                hint = if (valid == 0) "Start when ready" else "Keep going"
                if (!spec.rest.contains(v)) startRep(crossingMs(frame.tMs, v), v)
            }
            RepPhase.MOVING -> {
                accumulate(frame, v)
                if (spec.rest.contains(v)) {
                    newRep = finishRep(crossingMs(frame.tMs, v))
                    phase = RepPhase.REST
                } else if (frame.tMs - repStartMs > spec.maxRepS * 1500) {
                    newRep = record(frame.tMs, false, ReasonCodes.TOO_SLOW)
                    hint = "Rep took too long. Reset to the start position"
                    phase = RepPhase.WAITING
                }
            }
            RepPhase.HOLDING -> Unit
        }
        prevV = v
        prevMs = frame.tMs
        return update(v, true, newRep)
    }

    fun finish(): SessionSummary {
        val rules = catalog.sessionRules
        val first = firstMs
        val durationS = if (first == null) 0.0 else (lastMs - first) / 1000.0
        val reasons = mutableListOf<String>()
        val attempted = repList.size
        var holdS = 0.0

        if (spec.isHold) {
            closeHold()
            holdS = min(holdMs / 1000.0, spec.maxHoldS)
            if (enteredWithoutRest) reasons += ReasonCodes.NO_ENTRY_TRANSITION
            if (holdS < rules.minHoldS) reasons += ReasonCodes.HOLD_TOO_SHORT
            val spread = holdHipX.std + holdHipY.std
            if (holdHipX.n >= 10 && spread < MIN_LIVENESS_STD) reasons += ReasonCodes.STATIC_POSE
        } else {
            if (unsteady && valid > 0) {
                // Reps counted before enough still frames were seen cannot be trusted either.
                for (i in repList.indices) {
                    val r = repList[i]
                    if (r.valid) repList[i] = r.copy(valid = false, reason = ReasonCodes.UNSTEADY_TRACKING)
                }
                valid = 0
            }
            for (r in repList) {
                if (!r.valid && r.reason != null) reasons += r.reason
            }
            if (valid == 0) {
                reasons += ReasonCodes.NO_VALID_REPS
            } else if (valid.toDouble() / max(attempted, 1) < rules.minValidRatio) {
                reasons += ReasonCodes.LOW_VALID_RATIO
            }
            val durations = repList.filter { it.valid }.map { it.durationMs / 1000.0 }
            if (durations.size >= rules.replayMinReps && durationCv(durations) < rules.replayMaxDurationCv) {
                reasons += ReasonCodes.REPLAY_SUSPECTED
            }
            if (durationS > 0 && valid / (durationS / 60.0) > spec.maxRepsPerMin) reasons += ReasonCodes.RATE_IMPLAUSIBLE
        }

        val unique = reasons.distinct()
        val hard = unique.any { it in rules.hardReasons }
        val soft = unique.any { it !in ReasonCodes.REP_LEVEL }
        val verdict = when {
            hard -> Verdict.REJECTED
            soft -> Verdict.REVIEW
            else -> Verdict.VERIFIED
        }
        val visibility = if (frames == 0) 0.0 else visibleFrames.toDouble() / frames
        val quality = when {
            spec.isHold -> if (holdS > 0) 1.0 else 0.0
            attempted == 0 -> 0.0
            else -> valid.toDouble() / attempted
        }
        return SessionSummary(
            exerciseKey = spec.key,
            rulesVersion = catalog.rulesVersion,
            durationS = durationS,
            repsAttempted = attempted,
            repsValid = valid,
            holdS = holdS,
            formScore = roundHalfUp(quality * visibility, 3),
            verdict = verdict,
            reasons = unique,
            reps = repList.toList(),
        )
    }

    // ── metric ──────────────────────────────────────────────────────────

    private fun sideAngle(f: PoseFrame, s: String): Double? {
        val j = spec.joints
        val a = f.get(s, j[0]) ?: return null
        val b = f.get(s, j[1]) ?: return null
        val c = f.get(s, j[2]) ?: return null
        val minLik = catalog.minLikelihood
        if (a.likelihood < minLik || b.likelihood < minLik || c.likelihood < minLik) return null
        return angleDeg(a, b, c)
    }

    private fun metric(f: PoseFrame): Double? {
        val left = sideAngle(f, LEFT)
        val right = sideAngle(f, RIGHT)
        return when (spec.sides) {
            Metric.SIDES_MEAN -> if (left == null || right == null) null else (left + right) / 2
            Metric.SIDES_MIN -> when {
                left == null -> right
                right == null -> left
                else -> min(left, right)
            }
            else -> {
                side = pickSide(f, left != null, right != null)
                when (side) {
                    LEFT -> left
                    RIGHT -> right
                    else -> null
                }
            }
        }
    }

    /** The side the camera sees best, sticky so the angle does not flip between sides. */
    private fun pickSide(f: PoseFrame, leftOk: Boolean, rightOk: Boolean): String? {
        if (!leftOk && !rightOk) return null
        if (!rightOk) return LEFT
        if (!leftOk) return RIGHT
        fun score(s: String) = spec.joints.sumOf { f.get(s, it)?.likelihood ?: 0.0 }
        val l = score(LEFT)
        val r = score(RIGHT)
        val current = side ?: return if (l >= r) LEFT else RIGHT
        val other = if (current == LEFT) RIGHT else LEFT
        val margin = 0.15 * spec.joints.size
        return if ((if (current == LEFT) r - l else l - r) > margin) other else current
    }

    private fun torso(f: PoseFrame, s: String): Double? {
        val sh = f.get(s, "shoulder") ?: return null
        val h = f.get(s, "hip") ?: return null
        val d = sh.distanceTo(h)
        return if (d > 0) d else null
    }

    // ── reps ────────────────────────────────────────────────────────────

    private fun sampleRestLimbs(f: PoseFrame) {
        val j = spec.joints
        val minLik = catalog.minLikelihood
        for ((s, stats) in restLimbs) {
            val a = f.get(s, j[0]) ?: continue
            val b = f.get(s, j[1]) ?: continue
            val c = f.get(s, j[2]) ?: continue
            if (a.likelihood < minLik || b.likelihood < minLik || c.likelihood < minLik) continue
            stats.first.add(a.distanceTo(b))
            stats.second.add(b.distanceTo(c))
        }
    }

    /**
     * True once enough still frames show the tracker is too noisy to judge reps. Exercises that
     * read the better-tracked side are bounded by the steadier side; exercises that read both
     * sides (lunges, high knees, jumping jacks) by the noisier one, since its errors reach the metric too.
     */
    private val unsteady: Boolean
        get() {
            val cvs = restLimbs.values.filter { it.first.n >= MIN_REST_SAMPLES }.map { (it.first.cv + it.second.cv) / 2 }
            if (cvs.isEmpty()) return false
            return (if (spec.sides == Metric.SIDES_BEST) cvs.min() else cvs.max()) > MAX_REST_LIMB_CV
        }

    /**
     * When the angle crossed the rest-zone edge, interpolated between the previous frame and this
     * one. Rep durations then do not depend on where frames happen to fall: at 7 fps the frame
     * grid alone would shift a rep's measured length by up to 140 ms.
     */
    private fun crossingMs(tMs: Long, v: Double): Long {
        val pv = prevV
        val pt = prevMs
        if (pv == null || pt == null || tMs <= pt || v == pv) return tMs
        val f = ((spec.rest.threshold - pv) / (v - pv)).coerceIn(0.0, 1.0)
        return pt + ((tMs - pt) * f).roundToLong()
    }

    private fun startRep(tMs: Long, v: Double) {
        phase = RepPhase.MOVING
        repStartMs = tMs
        reachedPeak = false
        peakValue = v
        repFrames = 0
        repInvisible = 0
        repFormBreaks = 0
        repWrongPosition = 0
        repGlitches = 0
        peakSpreads.clear()
        bone1.reset()
        bone2.reset()
    }

    private fun accumulate(f: PoseFrame, v: Double) {
        repFrames++
        val towardPeak = if (spec.peak.below != null) v < peakValue else v > peakValue
        if (towardPeak) peakValue = v
        val atPeak = spec.peak.contains(v)
        if (atPeak) reachedPeak = true

        val s = side ?: LEFT
        if (!positionOk(f)) repWrongPosition++
        for (rule in spec.form) {
            when (rule.type) {
                FormRule.TYPE_ORIENTATION -> Unit
                FormRule.TYPE_ANKLE_SPREAD -> {
                    val spread = if (atPeak) ankleSpread(f) else null
                    if (spread != null) peakSpreads += spread
                }
                else -> {
                    val a = f.get(s, rule.joints[0])
                    val b = f.get(s, rule.joints[1])
                    val c = f.get(s, rule.joints[2])
                    if (a != null && b != null && c != null && angleDeg(a, b, c) < rule.min) repFormBreaks++
                }
            }
        }

        val t = torso(f, s)
        val a = f.get(s, spec.joints[0])
        val b = f.get(s, spec.joints[1])
        val c = f.get(s, spec.joints[2])
        if (t != null && a != null && b != null && c != null && spec.sides == Metric.SIDES_BEST) {
            bone1.add(a.distanceTo(b) / t)
            bone2.add(b.distanceTo(c) / t)
        }
        hint = if (reachedPeak) "Good. Come back up" else towardPeakHint()
    }

    private fun towardPeakHint(): String = when (spec.key) {
        "pushup", "squat", "lunge" -> "Go lower"
        "jumping_jack" -> "Arms all the way up"
        "high_knees" -> "Knee higher"
        else -> "Full range"
    }

    /** Every orientation rule holds (or cannot be judged because a joint is hidden). */
    private fun positionOk(f: PoseFrame): Boolean {
        val s = side ?: LEFT
        for (rule in spec.form) {
            if (rule.type != FormRule.TYPE_ORIENTATION) continue
            val a = f.get(s, rule.joints[0]) ?: continue
            val b = f.get(s, rule.joints[1]) ?: continue
            val tilt = tiltFromHorizontalDeg(a, b)
            val off = if (rule.axis == "horizontal") tilt else 90 - tilt
            if (off > rule.maxDeg) return false
        }
        return true
    }

    /**
     * Ankle distance in torso lengths (shoulder midpoint to hip midpoint). The torso is the
     * longest, steadiest segment a front camera sees; hip width is short and jitters.
     */
    private fun ankleSpread(f: PoseFrame): Double? {
        val la = f.get(LEFT, "ankle") ?: return null
        val ra = f.get(RIGHT, "ankle") ?: return null
        val ls = f.get(LEFT, "shoulder") ?: return null
        val rs = f.get(RIGHT, "shoulder") ?: return null
        val lh = f.get(LEFT, "hip") ?: return null
        val rh = f.get(RIGHT, "hip") ?: return null
        val t = Landmark((ls.x + rs.x) / 2, (ls.y + rs.y) / 2, 1.0)
            .distanceTo(Landmark((lh.x + rh.x) / 2, (lh.y + rh.y) / 2, 1.0))
        return if (t > 0) la.distanceTo(ra) / t else null
    }

    private fun finishRep(tMs: Long): RepResult? {
        val durationS = (tMs - repStartMs) / 1000.0
        if (!reachedPeak) {
            // Movement that never got halfway to the peak is noise, not an attempt.
            val halfway = (spec.rest.threshold + spec.peak.threshold) / 2
            val pastHalf = if (spec.peak.below != null) peakValue < halfway else peakValue > halfway
            if (!pastHalf) return null
            hint = towardPeakHint()
            return record(tMs, false, ReasonCodes.PARTIAL_RANGE)
        }
        val reason: String? = when {
            unsteady -> ReasonCodes.UNSTEADY_TRACKING
            repFrames > 0 && repInvisible.toDouble() / repFrames > MAX_INVISIBLE_FRACTION -> ReasonCodes.LOW_VISIBILITY
            repGlitches > 0 || (bone1.n >= 3 && (bone1.cv > MAX_BONE_CV || bone2.cv > MAX_BONE_CV)) -> ReasonCodes.TRACKING_GLITCH
            durationS < spec.minRepS -> ReasonCodes.TOO_FAST
            durationS > spec.maxRepS -> ReasonCodes.TOO_SLOW
            repFrames > 0 && repWrongPosition.toDouble() / repFrames > MAX_FORM_BREAK_FRACTION -> ReasonCodes.WRONG_POSITION
            formBroken() -> ReasonCodes.FORM_BREAK
            else -> null
        }
        hint = when (reason) {
            null -> "Nice rep"
            ReasonCodes.TOO_FAST -> "Slow down. Control every rep"
            ReasonCodes.FORM_BREAK -> if (spec.key == "pushup") "Keep your body in a straight line" else "Watch your form"
            ReasonCodes.LOW_VISIBILITY, ReasonCodes.TRACKING_GLITCH -> "Stay fully in view of the camera"
            ReasonCodes.WRONG_POSITION -> "Get into the position shown for this exercise"
            ReasonCodes.UNSTEADY_TRACKING -> "Tracking is unsteady. Move closer or add light"
            else -> "That rep did not count"
        }
        return record(tMs, reason == null, reason)
    }

    private fun formBroken(): Boolean {
        for (rule in spec.form) {
            if (rule.type == FormRule.TYPE_ANKLE_SPREAD && median(peakSpreads) < rule.min) return true
        }
        val angleRules = spec.form.count { it.type == FormRule.TYPE_ANGLE }
        return angleRules > 0 && repFrames > 0 && repFormBreaks.toDouble() / (repFrames * angleRules) > MAX_FORM_BREAK_FRACTION
    }

    private fun record(tMs: Long, isValid: Boolean, reason: String?): RepResult {
        val rep = RepResult(
            index = repList.size,
            startMs = repStartMs - (firstMs ?: 0L),
            durationMs = tMs - repStartMs,
            peakValue = roundHalfUp(peakValue, 1),
            valid = isValid,
            reason = reason,
        )
        repList += rep
        if (isValid) valid++
        return rep
    }

    // ── hold ────────────────────────────────────────────────────────────

    private fun hold(f: PoseFrame, v: Double) {
        val inHold = spec.peak.contains(v) && positionOk(f)
        if (spec.rest.contains(v)) sawRest = true
        if (inHold) {
            val lastIn = holdLastInMs
            if (phase != RepPhase.HOLDING) {
                if (!everHeld) enteredWithoutRest = !sawRest
                everHeld = true
                phase = RepPhase.HOLDING
            } else if (lastIn != null) {
                holdMs += f.tMs - lastIn
            }
            holdLastInMs = f.tMs
            val s = side ?: LEFT
            val hip = f.get(s, "hip")
            val t = torso(f, s)
            if (hip != null && t != null) {
                holdHipX.add(hip.x / t)
                holdHipY.add(hip.y / t)
            }
            hint = "Hold it. Body straight"
        } else {
            val lastIn = holdLastInMs
            if (phase == RepPhase.HOLDING && lastIn != null && f.tMs - lastIn > HOLD_GRACE_MS) closeHold()
            if (phase != RepPhase.HOLDING) {
                phase = if (sawRest) RepPhase.REST else RepPhase.WAITING
                hint = if (everHeld) "Straighten your body to keep the timer running" else "Move into a plank"
            }
        }
    }

    private fun closeHold() {
        phase = if (sawRest) RepPhase.REST else RepPhase.WAITING
        holdLastInMs = null
    }

    private fun update(v: Double?, visible: Boolean, newRep: RepResult?) = EngineUpdate(
        validReps = valid,
        attemptedReps = repList.size,
        holdS = holdMs / 1000.0,
        phase = phase,
        metric = v,
        visible = visible,
        hint = hint,
        newRep = newRep,
    )
}

/** Coefficient of variation of rep durations; matches `services.exercises.duration_cv` on the server. */
fun durationCv(durations: List<Double>): Double {
    val values = durations.filter { it > 0 }
    if (values.size < 2) return 1.0
    val mean = values.sum() / values.size
    if (mean <= 0) return 1.0
    val variance = values.sumOf { (it - mean) * (it - mean) } / values.size
    return sqrt(variance) / mean
}

/** Median, so one noisy frame at the top of a rep can neither pass nor fail it. */
internal fun median(xs: List<Double>): Double {
    if (xs.isEmpty()) return 0.0
    val s = xs.sorted()
    val m = s.size / 2
    return if (s.size % 2 == 1) s[m] else (s[m - 1] + s[m]) / 2
}

/** Rounds non-negative values like Dart's `toStringAsFixed` does for the values the engine reports. */
internal fun roundHalfUp(v: Double, digits: Int): Double {
    val f = 10.0.pow(digits)
    return floor(v * f + 0.5) / f
}

/** Running mean and standard deviation (Welford), O(1) memory. */
internal class RunningStats {
    var n = 0
        private set
    private var mean = 0.0
    private var m2 = 0.0

    fun add(x: Double) {
        n++
        val d = x - mean
        mean += d / n
        m2 += d * (x - mean)
    }

    fun reset() {
        n = 0
        mean = 0.0
        m2 = 0.0
    }

    val std: Double get() = if (n < 2) 0.0 else sqrt(m2 / n)
    val cv: Double get() = if (mean == 0.0) 0.0 else std / mean
}
