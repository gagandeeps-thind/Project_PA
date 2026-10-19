package com.osiris.shared.presentation.community

import com.osiris.shared.domain.model.Community
import com.osiris.shared.domain.repository.CommunityRepository
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CommunitiesState(
    val mine: Loadable<List<Community>> = Loadable.Loading,
    val discover: Loadable<List<Community>> = Loadable.Loading,
)

/** Clubs: the player's own, and public ones to join (by tap, or by name and join code). */
class CommunitiesViewModel(
    private val communities: CommunityRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(CommunitiesState())
    val state: StateFlow<CommunitiesState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch {
            val mine = async { communities.mine() }
            val discover = async { communities.discover() }
            _state.value = CommunitiesState(Loadable.of(mine.await()), Loadable.of(discover.await()))
        }
    }

    fun join(slug: String, joinCode: String? = null) {
        scope.launch {
            val joined = communities.join(slug, joinCode).orShow() ?: return@launch
            show("Welcome to ${joined.name}.", UiMessage.Kind.SUCCESS)
            refresh()
        }
    }
}
