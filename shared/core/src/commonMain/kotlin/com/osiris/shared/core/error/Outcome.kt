package com.osiris.shared.core.error

import kotlin.coroutines.cancellation.CancellationException

/** The result of an operation that can fail with an [AppError]. */
sealed interface Outcome<out T> {
    data class Success<out T>(val value: T) : Outcome<T>
    data class Failure(val error: AppError) : Outcome<Nothing>

    val isSuccess: Boolean get() = this is Success

    fun getOrNull(): T? = (this as? Success)?.value
    fun errorOrNull(): AppError? = (this as? Failure)?.error

    /** The value, or throws the [AppError]. */
    fun getOrThrow(): T = when (this) {
        is Success -> value
        is Failure -> throw error
    }
}

inline fun <T, R> Outcome<T>.map(transform: (T) -> R): Outcome<R> = when (this) {
    is Outcome.Success -> Outcome.Success(transform(value))
    is Outcome.Failure -> this
}

inline fun <T> Outcome<T>.onSuccess(block: (T) -> Unit): Outcome<T> = also { if (it is Outcome.Success) block(it.value) }

inline fun <T> Outcome<T>.onFailure(block: (AppError) -> Unit): Outcome<T> = also { if (it is Outcome.Failure) block(it.error) }

/**
 * Runs [block] and captures any failure as an [Outcome.Failure]. Coroutine cancellation is
 * rethrown, never swallowed, so structured concurrency keeps working.
 */
inline fun <T> outcomeOf(block: () -> T): Outcome<T> = try {
    Outcome.Success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: Throwable) {
    Outcome.Failure(AppError.from(e))
}
