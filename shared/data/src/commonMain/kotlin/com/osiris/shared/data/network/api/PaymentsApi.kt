package com.osiris.shared.data.network.api

import com.osiris.shared.data.network.ApiClient
import com.osiris.shared.domain.wallet.GooglePlayVerification

class PaymentsApi(private val api: ApiClient) {
    suspend fun verifyGooglePlay(productId: String, purchaseToken: String): GooglePlayVerification =
        api.post(
            "/api/v2/payments/google-play/verify",
            ApiClient.body("product_id" to productId, "purchase_token" to purchaseToken),
        )
}
