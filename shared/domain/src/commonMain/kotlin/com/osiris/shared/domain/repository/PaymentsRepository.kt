package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.wallet.PurchaseVerification
import com.osiris.shared.domain.wallet.StoreEntitlements

/** Purchases are only ever granted by the server, whichever store sold them. Every verify is safe to repeat. */
interface PaymentsRepository {
    /** A Play Billing purchase; the server credits a purchase token once. */
    suspend fun verifyGooglePlay(productId: String, purchaseToken: String): Outcome<PurchaseVerification>

    /** A StoreKit 2 transaction (`jwsRepresentation`); the server credits a transaction once. */
    suspend fun verifyAppStore(signedTransaction: String): Outcome<PurchaseVerification>

    suspend fun entitlements(): Outcome<StoreEntitlements>
}
