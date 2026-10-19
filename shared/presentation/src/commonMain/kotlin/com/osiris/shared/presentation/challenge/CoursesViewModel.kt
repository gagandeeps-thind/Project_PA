package com.osiris.shared.presentation.challenge

import com.osiris.shared.domain.model.ChallengeDraft
import com.osiris.shared.domain.model.CourseSummary
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CoursesState(
    val courses: Loadable<List<CourseSummary>> = Loadable.Loading,
    val publishing: Boolean = false,
    /** The challenge just published: the screen opens it. */
    val openChallengeId: Int? = null,
)

/** The player's registered courses, and publishing a challenge on one. */
class CoursesViewModel(
    private val challenges: ChallengeRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(CoursesState())
    val state: StateFlow<CoursesState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch { _state.update { it.copy(courses = Loadable.of(challenges.myCourses())) } }
    }

    /** Build the draft once per publish dialog, so a retry keeps its idempotency key. */
    fun draft(course: CourseSummary, title: String, windowHours: Int, safetyNotes: String?) =
        ChallengeDraft(course.id, title, windowHours, safetyNotes)

    fun publish(draft: ChallengeDraft) {
        if (_state.value.publishing) return
        _state.update { it.copy(publishing = true) }
        scope.launch {
            val id = challenges.publish(draft).orShow()
            _state.update { it.copy(publishing = false, openChallengeId = id) }
            if (id != null) {
                show("Challenge published.", UiMessage.Kind.SUCCESS)
                refresh()
            }
        }
    }

    fun opened() = _state.update { it.copy(openChallengeId = null) }
}
