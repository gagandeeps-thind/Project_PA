package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.wallet.PurchaseVerification
import com.osiris.shared.domain.wallet.StoreEntitlements

class PaymentsApi(private val api: ApiClient) {
    suspend fun verifyGooglePlay(productId: String, purchaseToken: String): PurchaseVerification =
        api.post(
            "/api/v2/payments/google-play/verify",
            ApiClient.body("product_id" to productId, "purchase_token" to purchaseToken),
        )

    suspend fun verifyAppStore(signedTransaction: String): PurchaseVerification =
        api.post("/api/v2/payments/app-store/verify", ApiClient.body("signed_transaction" to signedTransaction))

    suspend fun entitlements(): StoreEntitlements = api.get("/api/v2/payments/entitlements")
}
