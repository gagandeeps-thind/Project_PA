package com.osiris.shared.core.error

/**
 * Every failure the shared code reports, in one closed hierarchy, so screens handle errors with
 * an exhaustive `when` instead of catching platform exceptions.
 *
 * [userMessage] is safe to show to a player; [cause] keeps the original for logs.
 */
sealed class AppError(
    open val userMessage: String,
    override val cause: Throwable? = null,
) : Exception(userMessage, cause) {

    /** The request never reached the server (no network, DNS, refused connection). Retry later. */
    data class Offline(override val cause: Throwable? = null) :
        AppError("Unable to connect to the server. Please check your internet connection.", cause)

    /** The server did not answer in time. Retry later. */
    data class Timeout(override val cause: Throwable? = null) :
        AppError("Connection timed out. Please check your network and try again.", cause)

    /** The session token is missing, expired or revoked. The app signs the player out. */
    data class Unauthorized(
        override val userMessage: String = "Your session has expired. Please sign in again.",
        val code: String? = null,
    ) : AppError(userMessage)

    /**
     * The server answered with an error status.
     *
     * @property code the v2 machine-readable code (e.g. `CHALLENGE_NOT_OPEN`), when sent.
     */
    data class Http(
        val status: Int,
        val code: String?,
        override val userMessage: String,
    ) : AppError(userMessage) {
        val isClientError: Boolean get() = status in 400..499
        val isServerError: Boolean get() = status >= 500
    }

    /** The server's answer did not have the expected shape (contract drift). */
    data class InvalidResponse(override val cause: Throwable? = null) :
        AppError("The server sent an unexpected response. Please update the app or try again later.", cause)

    /** Local storage (database, preferences, keychain) failed. */
    data class Storage(override val userMessage: String = "Could not save on this device.", override val cause: Throwable? = null) :
        AppError(userMessage, cause)

    /** Input rejected before it was sent. */
    data class Validation(override val userMessage: String) : AppError(userMessage)

    /** A device capability is missing or was refused (camera, location). */
    data class Permission(val permission: String, override val userMessage: String) : AppError(userMessage)

    /** Anything else. */
    data class Unexpected(override val cause: Throwable? = null) :
        AppError("An unexpected error occurred.", cause)

    /** True when the same request may succeed later without any change (network trouble, 5xx, 429). */
    val isTransient: Boolean
        get() = when (this) {
            is Offline, is Timeout -> true
            is Http -> isServerError || status == 429
            else -> false
        }

    companion object {
        /** Wraps any throwable; an [AppError] passes through unchanged. */
        fun from(t: Throwable): AppError = t as? AppError ?: Unexpected(t)
    }
}
