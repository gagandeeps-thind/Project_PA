package com.osiris.shared.domain.repository

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.wallet.GooglePlayVerification

/** Purchases are only ever granted by the server. */
interface PaymentsRepository {
    /** Safe to repeat: the server credits a purchase token once. */
    suspend fun verifyGooglePlay(productId: String, purchaseToken: String): Outcome<GooglePlayVerification>
}
