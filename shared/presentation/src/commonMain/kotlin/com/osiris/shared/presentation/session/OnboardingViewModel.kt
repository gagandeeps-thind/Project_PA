package com.osiris.shared.presentation.session

import com.osiris.shared.core.error.AppError
import com.osiris.shared.domain.model.Goal
import com.osiris.shared.domain.model.Registration
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.PlayerRepository
import com.osiris.shared.presentation.common.SharedViewModel
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Three steps: goal, location consent, account. Consent is never pre-ticked. */
data class OnboardingState(
    val step: Step = Step.GOAL,
    val goal: Goal = Goal.FITNESS,
    val locationConsent: Boolean = false,
    val displayName: String = "",
    val email: String = "",
    val password: String = "",
    val referralCode: String = "",
    val fieldErrors: Map<String, String> = emptyMap(),
    val busy: Boolean = false,
) {
    enum class Step { GOAL, CONSENT, ACCOUNT }

    val stepNumber: Int get() = step.ordinal + 1
    val stepCount: Int get() = Step.entries.size
    val canGoBack: Boolean get() = step != Step.GOAL && !busy
}

class OnboardingViewModel(
    private val auth: AuthRepository,
    private val player: PlayerRepository,
    /** From an invite or referral link, when the app was opened from one. */
    private val inviteToken: String? = null,
    referralCode: String? = null,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(OnboardingState(referralCode = referralCode.orEmpty()))
    val state: StateFlow<OnboardingState> = _state.asStateFlow()

    init {
        scope.launch { player.track("onboarding_viewed") }
    }

    fun selectGoal(goal: Goal) = _state.update { it.copy(goal = goal) }

    fun setLocationConsent(granted: Boolean) = _state.update { it.copy(locationConsent = granted) }

    fun onName(v: String) = _state.update { it.copy(displayName = v, fieldErrors = it.fieldErrors - Registration.FIELD_NAME) }

    fun onEmail(v: String) = _state.update { it.copy(email = v, fieldErrors = it.fieldErrors - Registration.FIELD_EMAIL) }

    fun onPassword(v: String) = _state.update { it.copy(password = v, fieldErrors = it.fieldErrors - Registration.FIELD_PASSWORD) }

    fun onReferralCode(v: String) = _state.update { it.copy(referralCode = v) }

    fun next() = _state.update {
        if (it.step == OnboardingState.Step.ACCOUNT) it else it.copy(step = OnboardingState.Step.entries[it.step.ordinal + 1])
    }

    fun back() = _state.update {
        if (!it.canGoBack) it else it.copy(step = OnboardingState.Step.entries[it.step.ordinal - 1])
    }

    /** Creates the account; on success the session state changes and the app root navigates. */
    fun create() {
        val s = _state.value
        if (s.busy) return
        val registration = Registration(
            email = s.email.trim(),
            password = s.password,
            displayName = s.displayName.trim(),
            goal = s.goal,
            locationConsent = s.locationConsent,
            referralCode = s.referralCode.trim().ifEmpty { null },
            inviteToken = inviteToken,
        )
        val errors = registration.validate()
        if (errors.isNotEmpty()) {
            _state.update { it.copy(fieldErrors = errors) }
            return
        }
        _state.update { it.copy(busy = true, fieldErrors = emptyMap()) }
        scope.launch {
            val error = auth.register(registration).errorOrNull()
            // A rejection about one field shows on that field, where the player is looking;
            // a snackbar can sit under the keyboard.
            val field = (error as? AppError.Http)?.code?.let(FIELD_FOR_CODE::get)
            when {
                error == null -> Unit
                field != null -> _state.update { it.copy(fieldErrors = mapOf(field to error.userMessage)) }
                else -> showError(error)
            }
            _state.update { it.copy(busy = false) }
        }
    }
}

/** Server error codes from `POST /api/v2/auth/register` that belong to one form field. */
private val FIELD_FOR_CODE = mapOf("INVALID_EMAIL" to Registration.FIELD_EMAIL)
