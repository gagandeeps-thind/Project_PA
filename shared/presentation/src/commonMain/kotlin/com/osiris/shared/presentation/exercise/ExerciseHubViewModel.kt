package com.osiris.shared.presentation.exercise

import com.osiris.shared.core.error.map
import com.osiris.shared.domain.exercise.ExerciseCatalog
import com.osiris.shared.domain.exercise.ExerciseCopy
import com.osiris.shared.domain.exercise.ExerciseSpec
import com.osiris.shared.domain.model.ExerciseHistory
import com.osiris.shared.domain.model.StoredSession
import com.osiris.shared.domain.model.SyncState
import com.osiris.shared.domain.repository.ExerciseRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

data class ExerciseTile(val spec: ExerciseSpec, val best: String?)

data class RecentSetRow(val id: String, val title: String, val time: String, val status: String, val tone: Tone) {
    enum class Tone { NEUTRAL, GOOD, WARN, BAD }
}

data class ExerciseHubState(
    val exercises: Loadable<List<ExerciseTile>> = Loadable.Loading,
    val recent: List<RecentSetRow> = emptyList(),
    val consented: Boolean = false,
    /** Show the consent sheet before opening this exercise. */
    val askConsentFor: ExerciseSpec? = null,
    /** Open the camera for this exercise. */
    val open: ExerciseSpec? = null,
)

/** Pick an exercise, see personal bests and recent sets. Asks for camera consent first. */
class ExerciseHubViewModel(
    private val exercises: ExerciseRepository,
    private val zone: TimeZone = TimeZone.currentSystemDefault(),
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ExerciseHubState())
    val state: StateFlow<ExerciseHubState> = _state.asStateFlow()
    private var catalog: ExerciseCatalog? = null
    private var history: ExerciseHistory = ExerciseHistory.EMPTY

    init {
        scope.launch {
            val result = exercises.catalog()
            catalog = result.getOrNull()
            _state.update { it.copy(exercises = Loadable.of(result.map { tiles() })) }
        }
        scope.launch { _state.update { it.copy(consented = exercises.consent()) } }
        refresh()
    }

    /** Reads local history at once, then syncs in the background and re-reads if anything changed. */
    fun refresh() {
        scope.launch {
            showHistory(exercises.history())
            if (exercises.sync()) showHistory(exercises.history())
        }
    }

    fun select(spec: ExerciseSpec) = _state.update {
        if (it.consented) it.copy(open = spec) else it.copy(askConsentFor = spec)
    }

    fun consentAnswered(allow: Boolean) {
        val spec = _state.value.askConsentFor ?: return
        _state.update { it.copy(askConsentFor = null) }
        if (!allow) return
        scope.launch {
            exercises.setConsent(true).orShow()?.takeIf { it }?.let { _state.update { s -> s.copy(consented = true, open = spec) } }
        }
    }

    /** The camera screen was opened (or closed again): clear the request and reload history. */
    fun opened() = _state.update { it.copy(open = null) }

    fun returned() = refresh()

    private fun showHistory(h: ExerciseHistory) {
        history = h
        _state.update { s ->
            s.copy(
                exercises = if (catalog != null) Loadable.Ready(tiles()) else s.exercises,
                recent = h.recent.map(::row),
            )
        }
    }

    private fun tiles(): List<ExerciseTile> = catalog?.exercises.orEmpty().map { spec ->
        ExerciseTile(spec, history.bests[spec.key]?.let { ExerciseCopy.best(spec, it) })
    }

    private fun row(s: StoredSession): RecentSetRow {
        val spec = catalog?.byKey(s.exerciseKey)
        val (status, tone) = when (s.syncState) {
            SyncState.PENDING -> "Waiting to upload" to RecentSetRow.Tone.NEUTRAL
            SyncState.FAILED -> "Not accepted" to RecentSetRow.Tone.BAD
            SyncState.SYNCED -> when (s.serverStatus) {
                "verified" -> "+${s.xpAwarded} XP" to RecentSetRow.Tone.GOOD
                "review" -> "Under review" to RecentSetRow.Tone.WARN
                else -> "Not verified" to RecentSetRow.Tone.BAD
            }
        }
        val t = s.startedAt.toLocalDateTime(zone)
        fun two(v: Int) = v.toString().padStart(2, '0')
        return RecentSetRow(
            id = s.id,
            title = "${spec?.name ?: s.exerciseKey} · ${ExerciseCopy.amount(spec, s.repsValid, s.holdS)}",
            time = "${t.year}-${two(t.month.ordinal + 1)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}",
            status = status,
            tone = tone,
        )
    }
}
