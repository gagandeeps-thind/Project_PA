package com.osiris.shared.data.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.data.network.api.PaymentsApi
import com.osiris.shared.domain.repository.PaymentsRepository
import com.osiris.shared.domain.wallet.PurchaseVerification
import com.osiris.shared.domain.wallet.StoreEntitlements

class PaymentsRepositoryImpl(private val api: PaymentsApi) : PaymentsRepository {
    override suspend fun verifyGooglePlay(productId: String, purchaseToken: String): Outcome<PurchaseVerification> =
        outcomeOf { api.verifyGooglePlay(productId, purchaseToken) }

    override suspend fun verifyAppStore(signedTransaction: String): Outcome<PurchaseVerification> =
        outcomeOf { api.verifyAppStore(signedTransaction) }

    override suspend fun entitlements(): Outcome<StoreEntitlements> = outcomeOf { api.entitlements() }
}
