package com.osiris.shared.presentation.community

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.model.ChallengeSummary
import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.model.Leaderboard
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CommunityDetail(
    val community: Community,
    val leaderboard: Leaderboard?,
    val challenges: List<ChallengeSummary>,
)

data class CommunityDetailState(val detail: Loadable<CommunityDetail> = Loadable.Loading, val left: Boolean = false)

class CommunityDetailViewModel(
    private val slug: String,
    private val communities: CommunityRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(CommunityDetailState())
    val state: StateFlow<CommunityDetailState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            val board = async { communities.leaderboard(slug) }
            val list = async { communities.challenges(slug) }
            val detail = when (val c = communities.community(slug)) {
                is Outcome.Failure -> Loadable.failed(c.error)
                // The board and challenge list are supplementary; the club page shows without them.
                is Outcome.Success -> Loadable.Ready(
                    CommunityDetail(c.value, board.await().getOrNull(), list.await().getOrNull().orEmpty()),
                )
            }
            _state.update { it.copy(detail = detail) }
        }
    }

    fun join(joinCode: String? = null) {
        scope.launch { communities.join(slug, joinCode).orShow()?.let { refresh() } }
    }

    fun leave() {
        scope.launch {
            communities.leave(slug).orShow() ?: return@launch
            _state.update { it.copy(left = true) }
        }
    }

    fun report() {
        scope.launch { communities.report(slug).orShow()?.let { show(it) } }
    }
}
