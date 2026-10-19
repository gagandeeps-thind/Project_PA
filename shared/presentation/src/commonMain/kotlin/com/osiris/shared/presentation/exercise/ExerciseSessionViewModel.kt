package com.osiris.shared.presentation.exercise

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.exercise.EngineUpdate
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseCopy
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.domain.exercise.FrameRateMeter
import com.osiris.shared.domain.exercise.PoseFrame
import com.osiris.shared.domain.exercise.PoseRecorder
import com.osiris.shared.domain.exercise.SessionSummary
import com.osiris.shared.domain.exercise.SlowTrackingDetector
import com.osiris.shared.domain.exercise.RepEngine
import com.osiris.shared.domain.exercise.Verdict
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.SetOutcome
import com.osiris.shared.domain.repository.ExerciseRepository
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
)

data class ExerciseSessionState(
    val spec: ExerciseSpec,
    val phase: Phase = Phase.READY,
    val hud: ExerciseHud,
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
            Phase.READY -> "START"
            Phase.COUNTING -> "FINISH"
            Phase.SAVING -> "SAVING…"
            Phase.DONE -> "DONE"
        }
    val labelPrompt: String get() = if (spec.isHold) "Seconds of good plank hold" else "Reps that should count"
    val slowWarning: String?
        get() = slowFps?.let { "This phone is tracking $it frames a second; ${spec.name.lowercase()} needs ${spec.minPoseFps.roundToInt()}. Some reps may not count. More light or closing other apps can help." }
}

/**
 * One camera set. The platform owns the camera and pose model and passes every [PoseFrame] to
 * [onFrame]; counting runs here, in shared code, identically on both phones. Only the summary is
 * saved and uploaded; frames and landmarks never leave the phone (except labeled QA recordings).
 */
class ExerciseSessionViewModel(
    private val spec: ExerciseSpec,
    private val catalog: ExerciseCatalog,
    private val exercises: ExerciseRepository,
    recordingAllowed: Boolean = false,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(
        ExerciseSessionState(spec = spec, hud = idleHud(), recordingAllowed = recordingAllowed),
    )
    val state: StateFlow<ExerciseSessionState> = _state.asStateFlow()

    private var engine: RepEngine? = null
    private var startedAt: Instant? = null
    private var meter = FrameRateMeter()
    private val slow = SlowTrackingDetector(spec.minPoseFps)
    private var recorder: PoseRecorder? = null
    private var lastUpdate: EngineUpdate? = null
    private var pending: Pair<SessionSummary, String?>? = null

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
        _state.update { it.copy(phase = ExerciseSessionState.Phase.COUNTING, hud = hud(null)) }
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
            _state.update { it.copy(phase = ExerciseSessionState.Phase.DONE, result = result(summary, outcome, perf)) }
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

    private fun result(s: SessionSummary, outcome: SetOutcome?, perf: String?) = SetResult(
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
    )
}
