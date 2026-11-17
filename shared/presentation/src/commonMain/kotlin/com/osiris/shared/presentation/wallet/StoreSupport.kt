package com.osiris.shared.presentation.wallet

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.data.payments.StoreAccount
import com.osiris.shared.domain.repository.AuthRepository
import com.osiris.shared.domain.repository.AuthState
import com.osiris.shared.domain.repository.PaymentsRepository
import com.osiris.shared.domain.wallet.PurchaseVerification
import com.osiris.shared.domain.wallet.StoreEntitlements

/**
 * The server's answer to a store purchase. [verification] is null when the server did not answer
 * 200, with [error] safe to show (503: purchases are switched off on the server).
 */
class StoreVerifyResult(val verification: PurchaseVerification?, val error: String?) {
    /** The server has recorded the purchase: StoreKit may `finish()` the transaction now. */
    val finish: Boolean get() = verification != null
}

/**
 * Store billing for both apps: the account binding each store carries for the signed-in player, and
 * the server calls. Platform purchase code stays in the apps (Play Billing, StoreKit 2).
 * Swift: `graph.store().appStoreAccountToken()`, `try await graph.store().verifyAppStore(signedTransaction:)`.
 *
 * @property sellsPass whether Osiris Pass and the Founder Pack are offered (`features.passProducts`).
 */
class StoreSupport(
    private val auth: AuthRepository,
    private val payments: PaymentsRepository,
    val sellsPass: Boolean,
) {
    private val userId: Int? get() = (auth.state.value as? AuthState.SignedIn)?.user?.id

    /** Play `obfuscatedAccountId` for the signed-in player; null when signed out. */
    fun playAccountId(): String? = userId?.let(StoreAccount::playObfuscatedAccountId)

    /** StoreKit 2 `appAccountToken` (a UUID string) for the signed-in player; null when signed out. */
    fun appStoreAccountToken(): String? = userId?.let(StoreAccount::appStoreAccountToken)

    /** Sends a StoreKit 2 `jwsRepresentation`; safe to repeat for the same transaction. */
    suspend fun verifyAppStore(signedTransaction: String): StoreVerifyResult =
        when (val r = payments.verifyAppStore(signedTransaction)) {
            is Outcome.Success -> StoreVerifyResult(r.value, null)
            is Outcome.Failure -> StoreVerifyResult(null, r.error.userMessage)
        }

    /** What the player's purchases from either store unlock now; null when the server cannot say. */
    suspend fun entitlements(): StoreEntitlements? = payments.entitlements().getOrNull()
}
