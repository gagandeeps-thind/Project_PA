package com.osiris.shared.presentation.challenge

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.CourseRoute
import com.osiris.shared.domain.model.ReportReason
import com.osiris.shared.domain.repository.ChallengeRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.ShareRequest
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChallengeDetail(val challenge: ChallengeSummary, val course: CourseRoute?)

data class ChallengeDetailState(
    val detail: Loadable<ChallengeDetail> = Loadable.Loading,
    val joining: Boolean = false,
    val share: ShareRequest? = null,
    /** Set after blocking the creator: the screen closes. */
    val closed: Boolean = false,
) {
    private val challenge get() = detail.valueOrNull?.challenge
    val canInvite: Boolean get() = challenge?.isOpen == true
    val canReport: Boolean get() = challenge != null && challenge?.isMine == false
    val reportReasons: List<ReportReason> get() = ReportReason.entries
}

class ChallengeDetailViewModel(
    private val challengeId: Int,
    private val challenges: ChallengeRepository,
    private val player: PlayerRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(ChallengeDetailState())
    val state: StateFlow<ChallengeDetailState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            val detail = when (val c = challenges.challenge(challengeId)) {
                is Outcome.Failure -> Loadable.failed(c.error)
                is Outcome.Success -> {
                    // The route is shown to the creator and to players who joined, not to browsers.
                    val course = if (c.value.isMine || c.value.myAttempt != null) {
                        challenges.course(challengeId).orShow()
                    } else {
                        null
                    }
                    Loadable.Ready(ChallengeDetail(c.value, course))
                }
            }
            _state.update { it.copy(detail = detail) }
        }
    }

    fun join() {
        if (_state.value.joining) return
        _state.update { it.copy(joining = true) }
        scope.launch {
            if (challenges.join(challengeId).orShow() != null) refresh()
            _state.update { it.copy(joining = false) }
        }
    }

    fun report(reason: ReportReason) {
        scope.launch { challenges.report(challengeId, reason).orShow()?.let { show(it) } }
    }

    fun blockCreator() {
        scope.launch {
            challenges.blockCreator(challengeId).orShow() ?: return@launch
            show("Blocked. You won't see this player's challenges.")
            _state.update { it.copy(closed = true) }
        }
    }

    fun invite() {
        scope.launch {
            challenges.invite(challengeId).orShow()?.let { text ->
                _state.update { it.copy(share = ShareRequest(text, "challenge_invite")) }
            }
        }
    }

    /** Share text for an accepted attempt's result, or null (the failure is shown). */
    suspend fun shareResult(attemptId: Int): String? = player.shareAchievement("challenge_result", attemptId).orShow()?.text

    fun shared(completed: Boolean) {
        val request = _state.value.share ?: return
        _state.update { it.copy(share = null) }
        if (completed) scope.launch { player.track("share_completed", mapOf("kind" to request.kind)) }
    }
}
