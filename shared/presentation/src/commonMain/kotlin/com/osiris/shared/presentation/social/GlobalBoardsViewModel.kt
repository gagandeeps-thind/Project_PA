package com.osiris.shared.presentation.social

import com.osiris.shared.domain.model.BoardExercise
import com.osiris.shared.domain.model.BoardKind
import com.osiris.shared.domain.model.BoardPeriod
import com.osiris.shared.domain.model.GlobalBoard
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class GlobalBoardsState(
    val kind: BoardKind = BoardKind.DISTANCE,
    val period: BoardPeriod = BoardPeriod.WEEK,
    val exercise: BoardExercise = BoardExercise.PUSHUP,
    val board: Loadable<GlobalBoard> = Loadable.Loading,
) {
    /** The exercise picker only applies to the reps board. */
    val showsExercise: Boolean get() = kind == BoardKind.REPS
}

/** Global distance, Pace Index, reps and rewards boards. */
class GlobalBoardsViewModel(
    private val communities: CommunityRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(GlobalBoardsState())
    val state: StateFlow<GlobalBoardsState> = _state.asStateFlow()
    private var loading: Job? = null

    init {
        refresh()
    }

    fun select(kind: BoardKind) = change { it.copy(kind = kind) }
    fun select(period: BoardPeriod) = change { it.copy(period = period) }
    fun select(exercise: BoardExercise) = change { it.copy(exercise = exercise) }

    fun refresh() {
        // A slower answer for the previous selection must not replace the current one.
        loading?.cancel()
        val s = _state.value
        loading = scope.launch {
            val result = communities.globalBoard(s.kind, s.period, s.exercise)
            _state.update { it.copy(board = Loadable.of(result)) }
        }
    }

    private fun change(edit: (GlobalBoardsState) -> GlobalBoardsState) {
        val before = _state.value
        val after = edit(before).copy(board = Loadable.Loading)
        if (after.copy(board = before.board) == before) return
        _state.value = after
        refresh()
    }
}
