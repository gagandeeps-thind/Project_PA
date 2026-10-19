package com.osiris.shared.presentation.common

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Base for every shared view model: a coroutine scope tied to the screen, and a queue of
 * short messages (snackbars on Android, banners on iOS).
 *
 * Android wraps it in an androidx `ViewModel` and calls [clear] from `onCleared`; iOS calls
 * [clear] when the SwiftUI view model is released. Tests pass a test dispatcher.
 */
abstract class SharedViewModel(dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate) {
    protected val scope: CoroutineScope = CoroutineScope(SupervisorJob() + dispatcher)

    private val _message = MutableStateFlow<UiMessage?>(null)

    /** The message to show now, or null. The screen calls [messageShown] once it is displayed. */
    val message: StateFlow<UiMessage?> = _message.asStateFlow()

    fun messageShown() {
        _message.value = null
    }

    protected fun show(text: String, kind: UiMessage.Kind = UiMessage.Kind.INFO) {
        _message.value = UiMessage(text, kind)
    }

    protected fun showError(error: AppError) = show(error.userMessage, UiMessage.Kind.ERROR)

    /** Shows the failure, if any, and returns the value or null. */
    protected fun <T> Outcome<T>.orShow(): T? = when (this) {
        is Outcome.Success -> value
        is Outcome.Failure -> {
            showError(error)
            null
        }
    }

    open fun clear() {
        scope.cancel()
    }
}

/** A short, dismissible message. */
data class UiMessage(val text: String, val kind: Kind = Kind.INFO) {
    enum class Kind { INFO, SUCCESS, ERROR }
}
