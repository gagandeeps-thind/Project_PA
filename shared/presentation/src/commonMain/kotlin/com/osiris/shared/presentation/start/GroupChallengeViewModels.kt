package com.osiris.shared.presentation.start

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.Connection
import com.osiris.shared.domain.model.GroupChallenge
import com.osiris.shared.domain.model.GroupChallenges
import com.osiris.shared.domain.model.NewGroupChallenge
import com.osiris.shared.domain.model.TrainingActivity
import com.osiris.shared.domain.model.TrainingSession
import com.osiris.shared.domain.model.WeeklyProgress
import com.osiris.shared.domain.repository.GroupChallengeRepository
import com.osiris.shared.domain.repository.TrainingRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class GroupChallengesState(
    val lists: Loadable<GroupChallenges> = Loadable.Loading,
    val connections: List<Connection> = emptyList(),
    val activities: List<TrainingActivity> = emptyList(),
    val busy: Boolean = false,
    /** The challenge just created; the screen opens it. */
    val created: GroupChallenge? = null,
)

/** Group challenges: mine, invites and ones from connections, plus the create form's data. */
class GroupChallengesViewModel(
    private val groups: GroupChallengeRepository,
    private val training: TrainingRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(GroupChallengesState())
    val state: StateFlow<GroupChallengesState> = _state.asStateFlow()

    init {
        load()
        scope.launch { training.connections().getOrNull()?.let { c -> _state.update { it.copy(connections = c) } } }
        scope.launch { training.activities().getOrNull()?.let { a -> _state.update { it.copy(activities = a) } } }
    }

    fun load() {
        scope.launch { _state.update { it.copy(lists = Loadable.of(groups.all())) } }
    }

    fun create(challenge: NewGroupChallenge) {
        _state.update { it.copy(busy = true) }
        scope.launch {
            val made = groups.create(challenge).orShow()
            _state.update { it.copy(busy = false, created = made) }
            if (made != null) load()
        }
    }

    fun createdOpened() = _state.update { it.copy(created = null) }
}

data class GroupChallengeDetailState(val challenge: Loadable<GroupChallenge> = Loadable.Loading, val busy: Boolean = false)

class GroupChallengeDetailViewModel(
    private val id: Int,
    private val groups: GroupChallengeRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(GroupChallengeDetailState())
    val state: StateFlow<GroupChallengeDetailState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        scope.launch { _state.update { it.copy(challenge = Loadable.of(groups.detail(id))) } }
    }

    fun join() = act { groups.join(id) }

    fun leave() = act { groups.leave(id) }

    fun cancel() = act { groups.cancel(id) }

    private fun act(call: suspend () -> Outcome<GroupChallenge>) {
        _state.update { it.copy(busy = true) }
        scope.launch {
            val updated = call().orShow()
            _state.update { s -> s.copy(busy = false, challenge = updated?.let { Loadable.Ready(it) } ?: s.challenge) }
        }
    }
}

data class ProgressState(
    val weeks: List<WeeklyProgress> = emptyList(),
    val sessions: Loadable<List<TrainingSession>> = Loadable.Loading,
    /** null shows every activity. */
    val activity: String? = null,
    val detail: TrainingSession? = null,
    /** Activity key to display name, for the filter chips and session titles. */
    val names: Map<String, String> = emptyMap(),
    /** A workout import (Health Connect on Android) is running. */
    val importing: Boolean = false,
    /** How the last import went, or why it could not start. */
    val importStatus: String? = null,
)

/**
 * Profile → Progress: weekly volume, recent sessions, one session's charts, and importing workouts
 * from the platform's health store.
 */
class ProgressViewModel(
    private val training: TrainingRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ProgressState())
    val state: StateFlow<ProgressState> = _state.asStateFlow()

    init {
        scope.launch {
            training.activities().getOrNull()?.let { list -> _state.update { it.copy(names = list.associate { a -> a.key to a.name }) } }
        }
        refresh()
    }

    fun refresh() {
        scope.launch { training.progress().getOrNull()?.let { p -> _state.update { it.copy(weeks = p.weeks) } } }
        loadSessions()
    }

    /**
     * Runs the platform's [import], which uploads past workouts and returns how many were saved. It runs
     * here, not in the screen, so a rotation neither cancels it mid-upload nor loses the result.
     */
    fun importWorkouts(import: suspend () -> Outcome<Int>) {
        if (_state.value.importing) return
        _state.update { it.copy(importing = true, importStatus = "Importing…") }
        scope.launch {
            val status = when (val result = import()) {
                is Outcome.Success -> if (result.value == 0) "No new workouts to import." else "Imported ${result.value} workout(s)."
                is Outcome.Failure -> result.error.userMessage
            }
            _state.update { it.copy(importing = false, importStatus = status) }
            refresh()
        }
    }

    /** Why an import could not start (access refused, health store missing). */
    fun importUnavailable(reason: String) = _state.update { it.copy(importStatus = reason) }

    fun filter(activity: String?) {
        _state.update { it.copy(activity = activity) }
        loadSessions()
    }

    fun open(id: Int) {
        scope.launch { training.session(id).orShow()?.let { s -> _state.update { it.copy(detail = s) } } }
    }

    fun close() = _state.update { it.copy(detail = null) }

    private fun loadSessions() {
        val activity = _state.value.activity
        scope.launch { _state.update { it.copy(sessions = Loadable.of(training.sessions(activity))) } }
    }
}
