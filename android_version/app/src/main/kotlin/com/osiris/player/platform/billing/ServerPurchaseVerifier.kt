package com.osiris.player.platform.billing

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.repository.PaymentsRepository

/**
 * Asks the Osiris API whether every product in a purchase is paid for; the API credits it once.
 * False, including when the API is unreachable, leaves the purchase unconsumed so it can be retried.
 */
class ServerPurchaseVerifier(private val payments: PaymentsRepository) : PurchaseVerifier {
    override suspend fun verify(
        packageName: String,
        signedData: String,
        signature: String,
        purchaseToken: String,
        productIds: List<String>,
    ): Boolean = productIds.all { productId ->
        (payments.verifyGooglePlay(productId, purchaseToken) as? Outcome.Success)?.value?.entitled == true
    }
}
