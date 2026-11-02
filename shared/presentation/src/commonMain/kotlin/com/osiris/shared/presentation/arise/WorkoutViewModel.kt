package com.osiris.shared.presentation.arise

import com.osiris.shared.domain.model.AriseWorkout
import com.osiris.shared.domain.repository.AriseRepository
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Whose workout this is: the owner's Exceed for a domain, or an attacker repeating the defender's. */
sealed interface WorkoutTarget {
    data class Exceed(val domainId: Int) : WorkoutTarget
    data class Attack(val attackId: Int) : WorkoutTarget
}

data class WorkoutState(
    val workout: AriseWorkout? = null,
    /** Sets the player has done on camera (the server checks them on submit). */
    val done: Set<Int> = emptySet(),
    /** Seconds of rest left after the last set, or null. */
    val restLeft: Int? = null,
    val busy: Boolean = false,
    /** The workout counted: the domain is defended, or captured. */
    val finished: Boolean = false,
) {
    val allDone: Boolean get() = workout != null && done.size == workout.sets.size
}

/** The Exceed or attack workout, set by set: each set on camera, then its rest, then submit. */
class WorkoutViewModel(
    private val arise: AriseRepository,
    private val target: WorkoutTarget,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(WorkoutState())
    val state: StateFlow<WorkoutState> = _state.asStateFlow()
    private var rest: Job? = null

    init {
        when (target) {
            is WorkoutTarget.Exceed -> scope.launch {
                arise.exceed(target.domainId).orShow()?.let { w -> _state.update { it.copy(workout = w) } }
            }
            is WorkoutTarget.Attack -> _state.update { it.copy(workout = arise.cachedAttack(target.attackId)?.workout) }
        }
    }

    /** The camera screen came back from set [index]; its rest starts now. */
    fun setDone(index: Int) {
        val set = _state.value.workout?.sets?.getOrNull(index) ?: return
        _state.update { it.copy(done = it.done + index, restLeft = set.restS) }
        rest?.cancel()
        rest = scope.launch {
            for (left in set.restS - 1 downTo 0) {
                delay(1.seconds)
                _state.update { it.copy(restLeft = left.takeIf { l -> l > 0 }) }
            }
        }
    }

    fun skipRest() {
        rest?.cancel()
        _state.update { it.copy(restLeft = null) }
    }

    fun submit() {
        _state.update { it.copy(busy = true) }
        scope.launch {
            val finished = when (target) {
                is WorkoutTarget.Exceed -> arise.completeExceed(target.domainId).orShow()?.completed
                is WorkoutTarget.Attack -> arise.completeAttack(target.attackId).orShow()?.status?.let { it == "won" }
            }
            _state.update { it.copy(busy = false, finished = finished == true) }
            when (finished) {
                true -> {
                    val text = if (target is WorkoutTarget.Exceed) "Your workout now defends this domain." else "Domain captured!"
                    show(text, UiMessage.Kind.SUCCESS)
                }
                false -> show("Some sets are not verified yet. They may still be uploading; try again in a moment.")
                null -> Unit
            }
        }
    }
}
