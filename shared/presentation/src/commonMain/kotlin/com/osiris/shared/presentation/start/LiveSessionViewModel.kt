package com.osiris.shared.presentation.start

import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.domain.run.LocationFix
import com.osiris.shared.domain.training.Channel
import com.osiris.shared.domain.training.TrainingRecorder
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Clock
import kotlin.time.Duration.Companion.seconds
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class LivePhase { RECORDING, UPLOADING, SAVED, FAILED }

data class LiveState(
    val activity: TrainingActivity,
    val mode: StartMode,
    val elapsedS: Double = 0.0,
    val live: Map<Channel, Double?> = emptyMap(),
    val distanceM: Double = 0.0,
    val paused: Boolean = false,
    val devices: List<String> = emptyList(),
    val phase: LivePhase = LivePhase.RECORDING,
    val session: TrainingSession? = null,
    val posted: Boolean = false,
    /** Post or Just save was chosen: the screen can close. */
    val finished: Boolean = false,
)

/**
 * One live workout: sensor samples and GPS fixes go into a [TrainingRecorder]; Stop uploads the
 * session once (Retry re-sends the same body, so the server keeps one copy), then the player
 * chooses Post or Just save. The session is saved either way.
 */
class LiveSessionViewModel(
    private val training: TrainingRepository,
    activity: TrainingActivity,
    mode: StartMode,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    /** Ticks the elapsed time every second; tests drive the clock themselves. */
    tick: Boolean = true,
) : SharedViewModel(dispatcher) {
    private val startedAt = clock.now()
    private val recorder = TrainingRecorder(startedAt)
    private val _state = MutableStateFlow(LiveState(activity, mode))
    val state: StateFlow<LiveState> = _state.asStateFlow()
    private var ticker: Job? = null
    private var body: NewTrainingSession? = null

    @OptIn(ExperimentalUuidApi::class)
    private val clientId = Uuid.random().toString()

    init {
        if (tick) {
            ticker = scope.launch {
                while (isActive) {
                    delay(1.seconds)
                    refresh()
                }
            }
        }
    }

    fun onSample(channel: Channel, value: Double) {
        if (_state.value.phase != LivePhase.RECORDING) return
        recorder.add(channel, value, clock.now())
        refresh()
    }

    fun onFix(fix: LocationFix) {
        if (_state.value.phase != LivePhase.RECORDING) return
        recorder.addFix(fix, clock.now())
        refresh()
    }

    fun deviceConnected(name: String) = _state.update { if (name in it.devices) it else it.copy(devices = it.devices + name) }

    fun pause() {
        recorder.pause(clock.now())
        refresh()
    }

    fun resume() {
        recorder.resume(clock.now())
        refresh()
    }

    fun stop() {
        if (_state.value.phase != LivePhase.RECORDING) return
        ticker?.cancel()
        val now = clock.now()
        refresh()
        val s = _state.value
        body = NewTrainingSession(
            clientSessionId = clientId, activityKey = s.activity.key, mode = s.mode.wire, source = SOURCE,
            startedAt = startedAt.toString(), durationS = recorder.elapsedS(now).coerceAtLeast(1.0),
            distanceM = recorder.distanceM, series = recorder.series(), devices = s.devices,
        )
        upload()
    }

    fun retry() {
        if (_state.value.phase == LivePhase.FAILED) upload()
    }

    fun post(caption: String) {
        val session = _state.value.session ?: return
        scope.launch {
            training.post(session.id, caption).orShow()?.let { _state.update { it.copy(posted = true, finished = true) } }
        }
    }

    fun keep() = _state.update { it.copy(finished = it.session != null) }

    private fun upload() {
        val payload = body ?: return
        _state.update { it.copy(phase = LivePhase.UPLOADING) }
        scope.launch {
            val saved = training.upload(payload).orShow()
            _state.update { it.copy(phase = if (saved != null) LivePhase.SAVED else LivePhase.FAILED, session = saved) }
        }
    }

    private fun refresh() {
        val now = clock.now()
        _state.update {
            it.copy(
                elapsedS = recorder.elapsedS(now), distanceM = recorder.distanceM, paused = recorder.paused,
                live = Channel.entries.associateWith(recorder::latest),
            )
        }
    }

    private companion object {
        const val SOURCE = "sensor"
    }
}
