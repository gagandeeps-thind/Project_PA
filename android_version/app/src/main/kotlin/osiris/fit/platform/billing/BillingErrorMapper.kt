package osiris.fit.platform.billing

import com.android.billingclient.api.BillingClient.BillingResponseCode
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.wallet.PurchaseVerification

/**
 * Pure mapping utilities for Google Play Billing error codes, exponential backoff delays,
 * and subscription entitlement state transitions.
 */
object BillingErrorMapper {
    const val INITIAL_BACKOFF_MS = 1_000L
    const val MAX_BACKOFF_MS = 60_000L
    const val MAX_RETRY_ATTEMPTS = 5
    private const val MAX_SHIFT_EXPONENT = 10

    /**
     * Maps a Google Play `BillingResponseCode` to a structured [BillingFeedback] with
     * actionable user-facing copy.
     */
    fun fromResponseCode(responseCode: Int, debugMessage: String = ""): BillingFeedback {
        val code = mapErrorCode(responseCode)
        val message = userMessageFor(code, debugMessage)
        val isError = code != BillingErrorCode.USER_CANCELED
        return BillingFeedback(code = code, userMessage = message, isError = isError)
    }

    /** Maps a raw `BillingResponseCode` int to a typed [BillingErrorCode]. */
    fun mapErrorCode(responseCode: Int): BillingErrorCode = when (responseCode) {
        BillingResponseCode.USER_CANCELED -> BillingErrorCode.USER_CANCELED
        BillingResponseCode.ITEM_ALREADY_OWNED -> BillingErrorCode.ITEM_ALREADY_OWNED
        BillingResponseCode.SERVICE_UNAVAILABLE -> BillingErrorCode.SERVICE_UNAVAILABLE
        BillingResponseCode.DEVELOPER_ERROR -> BillingErrorCode.DEVELOPER_ERROR
        BillingResponseCode.BILLING_UNAVAILABLE -> BillingErrorCode.BILLING_UNAVAILABLE
        BillingResponseCode.ITEM_UNAVAILABLE -> BillingErrorCode.ITEM_UNAVAILABLE
        BillingResponseCode.NETWORK_ERROR -> BillingErrorCode.NETWORK_ERROR
        BillingResponseCode.SERVICE_DISCONNECTED -> BillingErrorCode.SERVICE_DISCONNECTED
        else -> BillingErrorCode.UNKNOWN
    }

    /** True when the response code represents a transient failure that should be retried with backoff. */
    fun isRetriable(responseCode: Int): Boolean =
        responseCode == BillingResponseCode.SERVICE_DISCONNECTED ||
            responseCode == BillingResponseCode.SERVICE_UNAVAILABLE ||
            responseCode == BillingResponseCode.NETWORK_ERROR

    /**
     * Computes the exponential backoff delay in milliseconds for reconnection attempt [attempt] (0-indexed).
     * Doubles on each attempt from [initialDelayMs] up to [maxDelayMs].
     */
    fun exponentialBackoffDelayMs(
        attempt: Int,
        initialDelayMs: Long = INITIAL_BACKOFF_MS,
        maxDelayMs: Long = MAX_BACKOFF_MS,
    ): Long {
        val safeAttempt = attempt.coerceIn(0, MAX_SHIFT_EXPONENT)
        val unclamped = initialDelayMs * (1L shl safeAttempt)
        return unclamped.coerceAtMost(maxDelayMs)
    }

    /**
     * Resolves the current [SubscriptionStatus] from active Google Play subscription records,
     * whether the user previously held a subscription, and whether a renewal grace period is active.
     */
    fun resolveSubscriptionStatus(
        activeSubscriptions: List<BillingPurchaseRecord>,
        hadPreviousSubscription: Boolean,
        inGracePeriod: Boolean,
    ): SubscriptionStatus {
        val hasVerifiedActive = activeSubscriptions.any { it.status == PurchaseEntitlementStatus.VERIFIED_AND_GRANTED }
        return when {
            hasVerifiedActive && inGracePeriod -> SubscriptionStatus.IN_GRACE_PERIOD
            hasVerifiedActive -> SubscriptionStatus.ACTIVE
            hadPreviousSubscription -> SubscriptionStatus.EXPIRED
            else -> SubscriptionStatus.NONE
        }
    }

    private fun userMessageFor(code: BillingErrorCode, debugMessage: String): String = when (code) {
        BillingErrorCode.USER_CANCELED ->
            "Purchase canceled. You were not charged."
        BillingErrorCode.ITEM_ALREADY_OWNED ->
            "You already own this item. Restoring your active entitlement from Google Play."
        BillingErrorCode.SERVICE_UNAVAILABLE ->
            "Google Play Store service is currently unavailable. Please check your connection and try again."
        BillingErrorCode.DEVELOPER_ERROR ->
            "Billing configuration error. Please ensure the app was installed from Google Play and is up to date."
        BillingErrorCode.BILLING_UNAVAILABLE ->
            "Google Play Billing is unavailable on this device or Google account."
        BillingErrorCode.ITEM_UNAVAILABLE ->
            "This product is not available for purchase in your country or region."
        BillingErrorCode.NETWORK_ERROR ->
            "Network error while contacting Google Play. Check your internet connection and try again."
        BillingErrorCode.SERVICE_DISCONNECTED ->
            "Disconnected from Google Play Store. Reconnecting automatically..."
        BillingErrorCode.VERIFICATION_FAILED ->
            "Purchase verification failed. If you were charged, your transaction will be refunded or restored shortly."
        BillingErrorCode.PURCHASES_UNAVAILABLE ->
            "Purchases are temporarily unavailable. Nothing was added to your account; we'll retry, " +
                "and Google Play refunds a purchase we can't confirm within 3 days."
        BillingErrorCode.UNKNOWN ->
            if (debugMessage.isNotBlank()) {
                "Unable to complete Google Play purchase ($debugMessage). Please try again."
            } else {
                "Unable to complete Google Play purchase. Please try again later."
            }
    }

    /**
     * Maps a failed server verification to the banner to show, or null when the purchase is simply
     * retried later without bothering the player (signed out, offline, timeout, rate limited).
     * The purchase is never consumed or acknowledged on a failure.
     */
    fun fromVerifyFailure(error: AppError): BillingFeedback? = when {
        error is AppError.Unauthorized || error is AppError.Offline || error is AppError.Timeout -> null
        error is AppError.Http && error.status == HTTP_TOO_MANY_REQUESTS -> null
        error is AppError.Http && error.status == HTTP_UNAVAILABLE -> feedback(BillingErrorCode.PURCHASES_UNAVAILABLE)
        error is AppError.Http && error.status == HTTP_CONFLICT -> BillingFeedback(
            code = BillingErrorCode.VERIFICATION_FAILED,
            userMessage = "This purchase was made for a different Osiris account. Sign in to that account to receive it.",
            isError = true,
        )
        else -> feedback(BillingErrorCode.VERIFICATION_FAILED)
    }

    /** The banner for a server answer: none when it granted the purchase, otherwise as [fromVerifyFailure]. */
    fun fromVerification(answer: Outcome<PurchaseVerification>): BillingFeedback? = when (answer) {
        is Outcome.Failure -> fromVerifyFailure(answer.error)
        is Outcome.Success -> if (answer.value.entitled) null else feedback(BillingErrorCode.VERIFICATION_FAILED)
    }

    /** The standard error banner for [code]. */
    fun feedback(code: BillingErrorCode) = BillingFeedback(code, userMessageFor(code, ""), isError = true)

    private const val HTTP_CONFLICT = 409
    private const val HTTP_TOO_MANY_REQUESTS = 429
    private const val HTTP_UNAVAILABLE = 503
}

