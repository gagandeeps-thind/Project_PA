package com.osiris.shared.presentation.navigation

import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.repository.DeviceSetupRepository
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** What the app root shows. The route guard: nothing past [PermissionPrimer] or [SignedOut] leaks through. */
sealed interface RootState {
    data object Restoring : RootState
    data object PermissionPrimer : RootState

    /** Sign-in or account creation; [invite] / [referral] prefill account creation. */
    data class SignedOut(val invite: String?, val referral: String?) : RootState

    /** The tabbed app; [pending] is a link to open once, then [AppNavigatorViewModel.pendingOpened]. */
    data class SignedIn(val pending: Destination?) : RootState
}

/**
 * App root: restores the session, gates on the permission primer and sign-in, and holds a deep
 * link until the player can see it (a challenge link opened while signed out opens after sign-in).
 * A signed-in session restores from secure storage, so the app reopens straight to Home.
 */
class AppNavigatorViewModel(
    private val auth: AuthRepository,
    private val setup: DeviceSetupRepository,
    private val links: DeepLinkParser,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val pending = MutableStateFlow<Destination?>(null)

    val state: StateFlow<RootState> = combine(auth.state, setup.primerCompleted, pending) { session, primerDone, link ->
        when {
            session == AuthState.Restoring -> RootState.Restoring
            session is AuthState.SignedIn -> RootState.SignedIn(link.takeUnless { it is Destination.Referral })
            !primerDone -> RootState.PermissionPrimer
            else -> RootState.SignedOut(
                invite = (link as? Destination.Invite)?.token,
                referral = (link as? Destination.Referral)?.code,
            )
        }
    }.stateIn(scope, SharingStarted.Eagerly, RootState.Restoring)

    init {
        scope.launch { if (auth.state.value == AuthState.Restoring) auth.restore() }
    }

    /** Called with every link the OS hands the app. Returns false for links the app does not handle. */
    fun open(link: String): Boolean {
        val destination = links.parse(link) ?: return false
        pending.value = destination
        return true
    }

    fun pendingOpened() {
        pending.value = null
    }
}
