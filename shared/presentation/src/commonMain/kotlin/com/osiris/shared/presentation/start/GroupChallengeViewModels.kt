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
)

/** Profile → Progress: weekly volume, recent sessions, and one session's charts. */
class ProgressViewModel(
    private val training: TrainingRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ProgressState())
    val state: StateFlow<ProgressState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch { training.progress().getOrNull()?.let { p -> _state.update { it.copy(weeks = p.weeks) } } }
        loadSessions()
    }

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
