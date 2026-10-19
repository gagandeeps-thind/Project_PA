package com.osiris.shared.presentation.session

import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** App root: restores the session once, then routes to sign-in or the home screen. */
class SessionViewModel(
    private val auth: AuthRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    val state: StateFlow<AuthState> = auth.state

    init {
        scope.launch { if (auth.state.value == AuthState.Restoring) auth.restore() }
    }
}
