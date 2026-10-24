package com.osiris.shared.presentation.run

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.common.Format
import com.osiris.shared.domain.model.AttemptSummary
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.ReasonCopy
import com.osiris.shared.domain.model.RunResult
import com.osiris.shared.domain.model.TodayData
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.RunRepository
import com.osiris.shared.domain.run.ActiveRun
import com.osiris.shared.domain.run.AutoPause
import com.osiris.shared.domain.run.CueInterval
import com.osiris.shared.domain.run.Daylight
import com.osiris.shared.domain.run.LatLng
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.run.Sport
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlin.time.Clock
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** What the run screen shows. Times and distances are pre-formatted for display. */
data class RunState(
    val challengeId: Int? = null,
    val position: LatLng? = null,
    val locating: Boolean = true,
    /** Why there is no position (permission refused, location off); cleared by the next fix. */
    val locationProblem: String? = null,
    val run: ActiveRun? = null,
    /** The recorded route for the map line (this session's fixes; not persisted). */
    val trace: List<LatLng> = emptyList(),
    val course: CourseRoute? = null,
    val nearby: List<ChallengeSummary> = emptyList(),
    val elapsed: String = "0:00",
    /** Elapsed time minus auto-paused stops. */
    val moving: String = "0:00",
    val distance: String = Format.km(0.0),
    val pace: String? = null,
    /** Elevation gained, once there is any. */
    val climb: String? = null,
    val paused: Boolean = false,
    /** Chosen before starting; a challenge run is always a run. */
    val sport: Sport = Sport.RUN,
    val autoPause: AutoPause = AutoPause.STOPS,
    /** Spoken cues; can be muted or re-timed mid-run. */
    val audioCues: Boolean = true,
    val cueInterval: CueInterval = CueInterval.KILOMETRE,
    val offline: Boolean = false,
    val busy: Boolean = false,
    val dialog: RunDialog? = null,
) {
    val recording: Boolean get() = run != null
    val title: String get() = if (challengeId == null) "RUN" else "CHALLENGE RUN"
    val canStart: Boolean get() = !busy && !recording && position != null
    val actionLabel: String get() = when {
        recording -> "FINISH RUN"
        position != null -> "START RUN"
        locationProblem != null -> "LOCATION OFF"
        else -> "LOCATING…"
    }
}

/** Dialogs the run flow asks the screen to show; each has a matching view model call. */
sealed interface RunDialog {
    /** A run open for over 12 hours: [RunViewModel.finish] or [RunViewModel.discard]. */
    data object StaleRun : RunDialog
    /** It's dark: [RunViewModel.start] with `confirmedLowLight = true`, or dismiss. */
    data object LowLight : RunDialog
    data object ConfirmDiscard : RunDialog
    data class Celebrate(
        val runId: Int,
        val title: String,
        val summary: String,
        val xp: String,
        val week: String?,
        val tomorrow: String?,
    ) : RunDialog
    /** Offer to register the route as a course: [RunViewModel.registerCourse] or dismiss. */
    data class OfferCourse(val runId: Int) : RunDialog
    data class Info(val title: String, val body: String) : RunDialog
}

/**
 * Run recording: live route, challenge course overlay, nearby challenges, and the
 * finish flow (verify, celebrate, challenge result, offer a course).
 *
 * The platform owns GPS: it subscribes while the screen is open, keeps a foreground service
 * while [RunState.recording], and passes every position to [onLocation].
 */
class RunViewModel(
    private val runs: RunRepository,
    private val challenges: ChallengeRepository,
    private val player: PlayerRepository,
    challengeId: Int? = null,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(RunState(challengeId = runs.active.value?.challengeId ?: challengeId))
    val state: StateFlow<RunState> = _state.asStateFlow()
    private var ticker: Job? = null
    private var nearbyLoaded = false
    private val _cues = MutableSharedFlow<String>(extraBufferCapacity = 4)

    /** Spoken announcements at the chosen [CueInterval]. The platform speaks them, screen on or off. */
    val cues: SharedFlow<String> = _cues.asSharedFlow()

    /** Last cue mark announced; -1 until a run is active (a recovered run is not caught up on). */
    private var cuedMark = -1

    init {
        scope.launch {
            runs.active.collect { run ->
                _state.update { it.copy(run = run).withClock() }
                if (run == null) cuedMark = -1 else cueIfDue(run)
            }
        }
        scope.launch { runs.offline.collect { off -> _state.update { it.copy(offline = off) } } }
        _state.value.challengeId?.let(::loadCourse)
        runs.active.value?.let { run ->
            startTicker()
            if (run.isStale(clock.now())) {
                _state.update { it.copy(dialog = RunDialog.StaleRun) }
            } else {
                show("Recovered your unfinished run. Keep going or tap FINISH.")
            }
        }
    }

    /** Every position from the platform, recording or not. */
    fun onLocation(fix: LocationFix) {
        _state.update {
            it.copy(
                position = fix.position,
                locating = false,
                locationProblem = null,
                trace = if (it.recording) it.trace + fix.position else it.trace,
            )
        }
        if (!nearbyLoaded) {
            nearbyLoaded = true
            loadNearby(fix.position)
        }
        if (runs.active.value != null) scope.launch { runs.addFix(fix, clock.now()) }
    }

    /** The platform could not get a position (permission refused, location off). */
    fun onLocationUnavailable(error: AppError) {
        _state.update { it.copy(locating = false, locationProblem = error.userMessage) }
    }

    fun toggle() {
        if (_state.value.recording) finish() else start()
    }

    fun selectSport(sport: Sport) = _state.update { if (it.recording) it else it.copy(sport = sport) }

    /** Chosen before starting: the recorded run and the server's moving time both use it. */
    fun setAutoPause(setting: AutoPause) = _state.update { if (it.recording) it else it.copy(autoPause = setting) }

    /** Mutes or unmutes cues, also mid-run. */
    fun setAudioCues(on: Boolean) = _state.update { it.copy(audioCues = on) }

    /** Changes how often cues speak, also mid-run; counting restarts from now, so nothing is announced at once. */
    fun setCueInterval(interval: CueInterval) {
        _state.update { it.copy(cueInterval = interval) }
        cuedMark = -1
        runs.active.value?.let(::cueIfDue)
    }

    private fun cueIfDue(run: ActiveRun) {
        val interval = _state.value.cueInterval
        val now = clock.now()
        val mark = interval.mark(run, now)
        if (cuedMark < 0) cuedMark = mark
        if (mark <= cuedMark) return
        cuedMark = mark
        if (_state.value.audioCues) _cues.tryEmit(cueText(interval, mark, run, now))
    }

    fun start(confirmedLowLight: Boolean = false) {
        val s = _state.value
        if (s.busy || s.recording) return
        val position = s.position ?: return show("Still finding your location. Try again in a moment.")
        val now = clock.now()
        if (!confirmedLowLight && Daylight.isDark(now, position.lat, position.lng)) {
            _state.update { it.copy(dialog = RunDialog.LowLight) }
            return
        }
        _state.update { it.copy(busy = true, dialog = null) }
        scope.launch {
            val sport = if (s.challengeId == null) s.sport else Sport.RUN
            runs.start(s.challengeId, now, sport, s.autoPause).orShow()?.let {
                _state.update { st -> st.copy(trace = listOf(position)) }
                startTicker()
            }
            _state.update { it.copy(busy = false) }
        }
    }

    fun finish() {
        if (_state.value.busy) return
        val run = runs.active.value ?: return
        _state.update { it.copy(busy = true, dialog = null) }
        scope.launch {
            when (val result = runs.finish(clock.now())) {
                is Outcome.Failure -> if (result.error is AppError.Offline) {
                    show("Points are saved on this phone. Tap FINISH again once you are back online.")
                } else {
                    showError(result.error)
                }
                is Outcome.Success -> {
                    stopTicker()
                    afterFinish(run, result.value)
                }
            }
            _state.update { it.copy(busy = false) }
        }
    }

    fun requestDiscard() = _state.update { it.copy(dialog = RunDialog.ConfirmDiscard) }

    fun discard() {
        scope.launch {
            runs.discard()
            stopTicker()
            _state.update { it.copy(trace = emptyList(), dialog = null) }
            show("Run discarded.")
        }
    }

    fun dismissDialog() {
        val dialog = _state.value.dialog
        _state.update { it.copy(dialog = null) }
        // After a celebration comes the course offer, as in the Flutter flow.
        if (dialog is RunDialog.Celebrate) _state.update { it.copy(dialog = RunDialog.OfferCourse(dialog.runId)) }
    }

    fun registerCourse(runId: Int, name: String) {
        _state.update { it.copy(dialog = null) }
        scope.launch {
            challenges.registerCourse(runId, name).orShow() ?: return@launch
            show("Course registered. Publish a challenge from My Courses.", UiMessage.Kind.SUCCESS)
        }
    }

    /** Returns the share text for the celebration's SHARE button, or null (the failure is shown). */
    suspend fun shareRun(runId: Int): String? = player.shareAchievement("run", runId).orShow()?.text

    private suspend fun afterFinish(run: ActiveRun, result: RunResult) {
        _state.update { it.copy(trace = emptyList()) }
        if (!result.accepted) {
            val reasons = result.reasons.joinToString("\n").ifEmpty { "The run did not pass verification." }
            _state.update { it.copy(dialog = RunDialog.Info("Run not verified", reasons)) }
            return
        }
        val challengeId = run.challengeId
        if (challengeId != null) {
            challenges.submitAttempt(challengeId, run.runId).orShow()?.let { attempt ->
                _state.update { it.copy(dialog = attemptDialog(attempt)) }
            }
        } else {
            val today = player.today(null).getOrNull()
            _state.update { it.copy(dialog = celebrate(run.runId, result, today)) }
        }
    }

    private fun loadCourse(challengeId: Int) {
        scope.launch {
            challenges.course(challengeId).orShow()?.let { course -> _state.update { it.copy(course = course) } }
        }
    }

    private fun loadNearby(position: LatLng) {
        scope.launch {
            // Discovery is supplementary on this screen; a failure stays silent.
            challenges.nearby(position).getOrNull()?.let { list -> _state.update { it.copy(nearby = list) } }
        }
    }

    private fun startTicker() {
        ticker?.cancel()
        ticker = scope.launch {
            while (isActive) {
                _state.update { it.withClock() }
                delay(1.seconds)
            }
        }
    }

    private fun stopTicker() {
        ticker?.cancel()
        ticker = null
    }

    private fun RunState.withClock(): RunState {
        val r = run ?: return copy(elapsed = "0:00", moving = "0:00", distance = Format.km(0.0), pace = null, climb = null, paused = false)
        val now = clock.now()
        return copy(
            elapsed = Format.duration(r.elapsed(now).inWholeSeconds.toDouble()),
            moving = Format.duration(r.moving(now).inWholeSeconds.toDouble()),
            distance = Format.km(r.distanceM),
            pace = r.paceSecPerKm(now)?.let { Format.duration(it) + " /km" },
            climb = r.elevationGainM.takeIf { it >= 1 }?.let { "${Format.fixed(it, 0)} m" },
            paused = r.paused,
        )
    }

    override fun clear() {
        stopTicker()
        super.clear()
    }

    companion object {
        private const val METRES_PER_KM = 1000.0

        /**
         * Distance cues: "2 kilometres. Time 11:04. Pace 5:32 per kilometre."
         * Time cues: "10 minutes. 1.84 kilometres. Pace 5:26 per kilometre."
         */
        fun cueText(interval: CueInterval, mark: Int, run: ActiveRun, now: kotlin.time.Instant): String {
            val pace = run.paceSecPerKm(now)?.let { " Pace ${Format.duration(it)} per kilometre." }.orEmpty()
            val minutes = interval.minutesAt(mark)
            if (minutes != null) {
                val km = Format.fixed(run.distanceM / METRES_PER_KM, 2)
                return "$minutes ${if (minutes == 1L) "minute" else "minutes"}. $km kilometres.$pace"
            }
            val unit = if (mark == 1) "kilometre" else "kilometres"
            return "$mark $unit. Time ${Format.duration(run.moving(now).inWholeSeconds.toDouble())}.$pace"
        }

        fun celebrate(runId: Int, result: RunResult, today: TodayData?) = RunDialog.Celebrate(
            runId = runId,
            title = if (today?.today?.completed == true) "Quest complete!" else "Run verified",
            summary = "${Format.distance(result.distanceM)} in ${Format.duration(result.durationSeconds)}",
            xp = "+${result.xpAwarded} XP",
            week = today?.week?.let { "This week: ${it.activeDays} of ${it.activeDaysTarget} active days" },
            tomorrow = today?.let { "Tomorrow: ${it.tomorrow.title}" },
        )

        fun attemptDialog(attempt: AttemptSummary): RunDialog.Info {
            val lines = buildList {
                val elapsed = attempt.elapsedSeconds
                if (elapsed != null && elapsed > 0) {
                    add("Your time: ${Format.duration(elapsed)}  •  Target: ${Format.duration(attempt.targetSeconds)}")
                }
                if (attempt.xpAwarded > 0) add("+${attempt.xpAwarded} XP")
                addAll(attempt.reasonCodes.map(ReasonCopy::explain))
            }
            return RunDialog.Info(attempt.resultTitle, lines.joinToString("\n"))
        }
    }
}
