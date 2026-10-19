package com.osiris.shared.presentation.common

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome

/** Screen data that is loading, ready, or failed with a message the player can act on. */
sealed interface Loadable<out T> {
    data object Loading : Loadable<Nothing>
    data class Ready<out T>(val value: T) : Loadable<T>
    data class Failed(val message: String, val canRetry: Boolean) : Loadable<Nothing>

    val valueOrNull: T? get() = (this as? Ready)?.value

    companion object {
        fun <T> of(outcome: Outcome<T>): Loadable<T> = when (outcome) {
            is Outcome.Success -> Ready(outcome.value)
            is Outcome.Failure -> failed(outcome.error)
        }

        fun failed(error: AppError): Failed = Failed(error.userMessage, canRetry = error !is AppError.Unauthorized)
    }
}
