package com.osiris.shared.presentation.exercise

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.exercise.EngineUpdate
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseCopy
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.domain.exercise.FrameRateMeter
import com.osiris.shared.domain.exercise.PoseFrame
import com.osiris.shared.domain.exercise.PoseRecorder
import com.osiris.shared.domain.exercise.RepEngine
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.exercise.SlowTrackingDetector
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.domain.model.PostCreateDraft
import com.osiris.shared.domain.model.SetOutcome
import com.osiris.shared.domain.repository.ExerciseRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlin.math.floor
import kotlin.math.roundToInt
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The HUD over the camera preview. Changes only when something the player sees changes. */
data class ExerciseHud(
    val count: String,
    val hint: String,
    /** "2 not counted", for rep exercises once some reps failed. */
    val notCounted: String?,
)

/** The result sheet after a set. */
data class SetResult(
    val title: String,
    val verdict: Verdict,
    val amount: String,
    val notCounted: String?,
    val reasons: List<String>,
    val sync: String,
    /** Debug builds: pose timing read-out from the platform. */
    val perf: String?,
    val currentSet: Int = 1,
    val totalSets: Int = 1,
    val canStartNextSet: Boolean = false,
    val canShareToFeed: Boolean = true,
    val postedToFeed: Boolean = false,
    /** The uploaded set's id, for the Start tab to link its session to; null until uploaded. */
    val uploadedSetId: String? = null,
    val setStartedAt: Instant? = null,
)

data class ExerciseSessionState(
    val spec: ExerciseSpec,
    val phase: Phase = Phase.READY,
    val hud: ExerciseHud,
    val currentSet: Int = 1,
    val totalSets: Int = 1,
    val targetRepsPerSet: Int = 0,
    val targetHoldSecondsPerSet: Int = 0,
    /** Set while tracking is too slow for this exercise: the frames per second, for the warning. */
    val slowFps: Int? = null,
    val cameraError: String? = null,
    /** QA builds only: offer the landmark recording toggle. */
    val recordingAllowed: Boolean = false,
    val recordLandmarks: Boolean = false,
    /** Waiting for the tester's label before the recording is saved. */
    val askLabel: Boolean = false,
    val result: SetResult? = null,
) {
    enum class Phase { READY, COUNTING, SAVING, DONE }

    val buttonLabel: String
        get() = when (phase) {
            Phase.READY -> if (totalSets > 1) "Start Set $currentSet/$totalSets" else "Start"
            Phase.COUNTING -> if (totalSets > 1) "Finish Set $currentSet/$totalSets" else "Finish"
            Phase.SAVING -> "SAVING…"
            Phase.DONE -> "Done"
        }

    val planBanner: String?
        get() = when {
            spec.isHold && targetHoldSecondsPerSet > 0 ->
                "Set $currentSet/$totalSets  •  Target ${targetHoldSecondsPerSet}s × $totalSets"
            !spec.isHold && targetRepsPerSet > 0 ->
                "Set $currentSet/$totalSets  •  Target $targetRepsPerSet × $totalSets"
            totalSets > 1 ->
                "Set $currentSet of $totalSets"
            else -> null
        }

    val labelPrompt: String get() = if (spec.isHold) "Seconds of good plank hold" else "Reps that should count"
    val slowWarning: String?
        get() = slowFps?.let {
            "This phone is tracking $it frames a second; ${spec.name.lowercase()} needs ${spec.minPoseFps.roundToInt()}. " +
                "Some reps may not count. More light or closing other apps can help."
        }
}

/**
 * One camera set (or multi-set Streak Start plan). The platform owns the camera and pose model and passes
 * every [PoseFrame] to [onFrame]; counting runs here, in shared code, identically on both phones.
 */
class ExerciseSessionViewModel(
    private val spec: ExerciseSpec,
    private val catalog: ExerciseCatalog,
    private val exercises: ExerciseRepository,
    recordingAllowed: Boolean = false,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    private val totalSets: Int = 1,
    private val targetRepsPerSet: Int = 0,
    private val targetHoldSecondsPerSet: Int = 0,
    private val player: PlayerRepository? = null,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(
        ExerciseSessionState(
            spec = spec,
            hud = idleHud(),
            currentSet = 1,
            totalSets = totalSets.coerceAtLeast(1),
            targetRepsPerSet = targetRepsPerSet.coerceAtLeast(0),
            targetHoldSecondsPerSet = targetHoldSecondsPerSet.coerceAtLeast(0),
            recordingAllowed = recordingAllowed,
        ),
    )
    val state: StateFlow<ExerciseSessionState> = _state.asStateFlow()

    private var engine: RepEngine? = null
    private var startedAt: Instant? = null
    private var meter = FrameRateMeter()
    private val slow = SlowTrackingDetector(spec.minPoseFps)
    private var recorder: PoseRecorder? = null
    private var lastUpdate: EngineUpdate? = null
    private var pending: Pair<SessionSummary, String?>? = null
    private var cumulativeReps = 0
    private var cumulativeHoldS = 0.0
    private var cumulativeDurationS = 0.0
    private var cumulativeXp = 0

    /** The camera (re)started: a reopened camera warms up again, so the rate window restarts. */
    fun onCameraStarted() {
        meter = FrameRateMeter()
        _state.update { it.copy(cameraError = null) }
    }

    fun onCameraFailed(error: AppError) = _state.update { it.copy(cameraError = error.userMessage) }

    /** Called for every pose frame, on any thread the platform likes but one at a time. */
    fun onFrame(frame: PoseFrame) {
        meter.add(frame.tMs)
        val fps = meter.fps
        val slowFps = if (slow.update(fps)) fps?.roundToInt() else null
        if (slowFps != _state.value.slowFps) _state.update { it.copy(slowFps = slowFps) }
        val e = engine ?: return
        recorder?.add(frame)
        val u = e.addFrame(frame)
        val prev = lastUpdate
        lastUpdate = u
        if (prev == null || prev.validReps != u.validReps || prev.attemptedReps != u.attemptedReps ||
            prev.hint != u.hint || floor(prev.holdS) != floor(u.holdS)
        ) {
            _state.update { it.copy(hud = hud(u)) }
        }
    }

    fun setRecordLandmarks(on: Boolean) = _state.update { if (it.recordingAllowed) it.copy(recordLandmarks = on) else it }

    fun start() {
        if (_state.value.phase != ExerciseSessionState.Phase.READY) return
        engine = RepEngine(spec, catalog)
        recorder = if (_state.value.recordingAllowed && _state.value.recordLandmarks) PoseRecorder() else null
        startedAt = clock.now()
        lastUpdate = null
        _state.update { it.copy(phase = ExerciseSessionState.Phase.COUNTING, hud = hud(null), result = null) }
    }

    /** [perf] is the platform's pose timing read-out (debug builds), shown on the result sheet. */
    fun finish(perf: String? = null) {
        val e = engine ?: return
        if (_state.value.phase != ExerciseSessionState.Phase.COUNTING) return
        engine = null
        val summary = e.finish()
        if (recorder != null) {
            pending = summary to perf
            _state.update { it.copy(phase = ExerciseSessionState.Phase.SAVING, askLabel = true) }
        } else {
            save(summary, perf)
        }
    }

    /** Advances to the next set in a multi-set Streak Start plan. */
    fun nextSet() {
        val s = _state.value
        if (s.phase != ExerciseSessionState.Phase.DONE || s.currentSet >= s.totalSets) return
        _state.update {
            it.copy(
                phase = ExerciseSessionState.Phase.READY,
                currentSet = s.currentSet + 1,
                hud = idleHud(),
                result = null,
            )
        }
    }

    /** Posts the completed camera-verified workout to People's Posts (`POST /api/v2/feed/posts`). */
    fun shareWorkoutToFeed(caption: String = "") {
        val p = player ?: return
        val s = _state.value
        val r = s.result
        if (r == null || r.postedToFeed) return
        scope.launch {
            val setsDone = s.currentSet.coerceAtLeast(1)
            val repsPerSet = if (s.targetRepsPerSet > 0) s.targetRepsPerSet else (cumulativeReps / setsDone).coerceAtLeast(1)
            val draft = PostCreateDraft(
                kind = "workout",
                caption = caption.ifBlank {
                    "Completed camera-verified ${spec.name} on Osiris!"
                },
                exerciseKey = spec.key,
                sets = setsDone,
                repsPerSet = if (spec.isHold) 0 else repsPerSet,
                totalReps = cumulativeReps,
                holdS = cumulativeHoldS,
                durationS = cumulativeDurationS,
                xpEarned = cumulativeXp,
            )
            p.createPost(draft).orShow() ?: return@launch
            _state.update { it.copy(result = it.result?.copy(postedToFeed = true)) }
            show("Workout shared to People's Posts!", UiMessage.Kind.SUCCESS)
        }
    }

    /** The tester's label for the QA recording, or null to discard it (unlabeled data tests nothing). */
    fun labelRecording(value: String?) {
        val (summary, perf) = pending ?: return
        pending = null
        val rec = recorder
        recorder = null
        _state.update { it.copy(askLabel = false) }
        val number = value?.trim()?.toDoubleOrNull()
        if (rec != null && number != null) {
            val recording = rec.finish(
                exerciseKey = spec.key,
                rulesVersion = summary.rulesVersion,
                recordedAt = clock.now(),
                labelReps = if (spec.isHold) null else number.roundToInt(),
                labelHoldS = if (spec.isHold) number else null,
            )
            scope.launch {
                exercises.saveRecording(recording).orShow()?.let { show("Landmarks saved: $it", UiMessage.Kind.SUCCESS) }
            }
        }
        save(summary, perf)
    }

    private fun save(summary: SessionSummary, perf: String?) {
        _state.update { it.copy(phase = ExerciseSessionState.Phase.SAVING) }
        scope.launch {
            val outcome = exercises.saveSet(summary, startedAt ?: clock.now()).getOrNull()
            cumulativeReps += summary.repsValid
            cumulativeHoldS += summary.holdS
            cumulativeDurationS += summary.durationS
            cumulativeXp += outcome?.xpAwarded ?: 0
            val done = result(summary, outcome, perf).copy(
                uploadedSetId = outcome?.takeIf { it.uploaded }?.clientSessionId?.ifEmpty { null },
                setStartedAt = startedAt,
            )
            _state.update { it.copy(phase = ExerciseSessionState.Phase.DONE, result = done) }
        }
    }

    private fun idleHud() = ExerciseHud(count = if (spec.isHold) "0 s" else "0", hint = spec.instructions, notCounted = null)

    private fun hud(u: EngineUpdate?): ExerciseHud {
        val failed = (u?.attemptedReps ?: 0) - (u?.validReps ?: 0)
        return ExerciseHud(
            count = if (spec.isHold) "${Format.fixed(u?.holdS ?: 0.0, 0)} s" else "${u?.validReps ?: 0}",
            hint = u?.hint?.takeIf { it.isNotEmpty() } ?: "Get into position",
            notCounted = if (!spec.isHold && failed > 0) "$failed not counted" else null,
        )
    }

    private fun result(s: SessionSummary, outcome: SetOutcome?, perf: String?): SetResult {
        val cur = _state.value.currentSet
        val tot = _state.value.totalSets
        return SetResult(
            title = ExerciseCopy.verdictTitle(s.verdict),
            verdict = s.verdict,
            amount = "${spec.name}: ${ExerciseCopy.amount(spec, s.repsValid, s.holdS)}",
            notCounted = if (!spec.isHold && s.repsAttempted > s.repsValid) "${s.repsAttempted - s.repsValid} reps did not count" else null,
            reasons = s.reasons.map(ExerciseCopy::reason),
            sync = when {
                outcome == null -> "This set could not be saved on your phone."
                outcome.uploaded && outcome.xpAwarded > 0 -> "+${outcome.xpAwarded} XP"
                outcome.uploaded -> "Uploaded. No XP for this set."
                else -> "Saved on your phone. It will upload when you are online."
            },
            perf = perf,
            currentSet = cur,
            totalSets = tot,
            canStartNextSet = cur < tot,
            canShareToFeed = player != null && (s.repsValid > 0 || s.holdS > 0.0),
            postedToFeed = false,
        )
    }
}
