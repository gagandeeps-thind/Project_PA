package com.osiris.shared.presentation.start

import com.osiris.shared.domain.model.ActivityKind
import com.osiris.shared.domain.model.GroupChallenges
import com.osiris.shared.domain.model.NewTrainingSession
import com.osiris.shared.domain.model.Quote
import com.osiris.shared.domain.model.StartMode
import com.osiris.shared.domain.model.SuggestedChallenge
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.model.TrainingSummary
import com.osiris.shared.domain.repository.GroupChallengeRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlin.time.Clock
import kotlin.time.Instant
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class StartState(
    val mode: StartMode,
    val activities: List<TrainingActivity> = emptyList(),
    val selected: TrainingActivity? = null,
    val quote: Quote? = null,
    /** Train only: results and charts of [selected]. */
    val summary: Loadable<TrainingSummary>? = null,
    /** Challenge only: official and group challenges. */
    val groups: Loadable<GroupChallenges>? = null,
    /** Challenge only: suggested course challenges. */
    val suggested: List<SuggestedChallenge> = emptyList(),
    /** A camera set just saved, waiting for Post or Just save. */
    val pendingPost: TrainingSession? = null,
)

/** The Train or Challenge page: activity ribbon, quote, start button, and the sections below it. */
class StartViewModel(
    private val training: TrainingRepository,
    private val groups: GroupChallengeRepository,
    private val player: PlayerRepository,
    mode: StartMode,
    private val clock: Clock = Clock.System,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(StartState(mode))
    val state: StateFlow<StartState> = _state.asStateFlow()

    init {
        scope.launch {
            training.activities().orShow()?.let { list ->
                val first = list.firstOrNull { it.key == DEFAULT_ACTIVITY } ?: list.firstOrNull()
                _state.update { it.copy(activities = list, selected = first) }
                loadSummary()
            }
        }
        scope.launch { training.quote().getOrNull()?.let { q -> _state.update { it.copy(quote = q) } } }
        if (mode == StartMode.CHALLENGE) loadChallenges()
    }

    fun select(activity: TrainingActivity) {
        _state.update { it.copy(selected = activity) }
        scope.launch { loadSummary() }
    }

    /** Back from a session or a challenge: the numbers below the start button may have moved. */
    fun refresh() {
        scope.launch { loadSummary() }
        if (_state.value.mode == StartMode.CHALLENGE) loadChallenges()
    }

    /** The camera coach uploaded a set; record it as this page's session, linked to that set. */
    @OptIn(ExperimentalUuidApi::class)
    fun saveCameraSet(activityKey: String, setId: String, startedAt: Instant) {
        val body = NewTrainingSession(
            clientSessionId = Uuid.random().toString(), activityKey = activityKey, mode = _state.value.mode.wire,
            source = SOURCE_CAMERA, // The server takes the duration from the verified set.
            startedAt = startedAt.toString(), durationS = 1.0,
            exerciseSetId = setId,
        )
        scope.launch {
            training.upload(body).orShow()?.let { saved -> _state.update { it.copy(pendingPost = saved) } }
            refresh()
        }
    }

    fun post(caption: String) {
        val session = _state.value.pendingPost ?: return
        _state.update { it.copy(pendingPost = null) }
        scope.launch { training.post(session.id, caption).orShow()?.let { show("Posted to your feed") } }
    }

    fun keep() = _state.update { it.copy(pendingPost = null) }

    /** Camera activities go to the camera coach; everything else records a live session. */
    fun isCamera(activity: TrainingActivity) = activity.kind == ActivityKind.CAMERA

    fun now(): Instant = clock.now()

    private suspend fun loadSummary() {
        val key = _state.value.selected?.key ?: return
        if (_state.value.mode != StartMode.TRAIN) return
        _state.update { it.copy(summary = it.summary ?: Loadable.Loading) }
        val result = Loadable.of(training.summary(key))
        // A slower answer for an activity the player has since left is dropped.
        if (_state.value.selected?.key == key) _state.update { it.copy(summary = result) }
    }

    private fun loadChallenges() {
        scope.launch { _state.update { it.copy(groups = Loadable.of(groups.all())) } }
        scope.launch {
            player.suggestedChallenges().getOrNull()?.let { list -> _state.update { it.copy(suggested = list) } }
        }
    }

    private companion object {
        const val DEFAULT_ACTIVITY = "run"
        const val SOURCE_CAMERA = "camera"
    }
}
