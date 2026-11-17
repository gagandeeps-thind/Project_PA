package osiris.fit.platform.billing

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.repository.PaymentsRepository
import com.osiris.shared.domain.wallet.PurchaseVerification

/**
 * Asks the Osiris API whether every product in a purchase is paid for; the API credits it once
 * (quantity included) and answers with its own figures. Any failure, including the API being
 * unreachable or switched off (503), is returned as is and leaves the purchase unconsumed for a retry.
 */
class ServerPurchaseVerifier(private val payments: PaymentsRepository) : PurchaseVerifier {
    override suspend fun verify(
        packageName: String,
        signedData: String,
        signature: String,
        purchaseToken: String,
        productIds: List<String>,
    ): Outcome<PurchaseVerification> {
        val answers = productIds.map { productId ->
            when (val answer = payments.verifyGooglePlay(productId, purchaseToken)) {
                is Outcome.Failure -> return answer
                is Outcome.Success -> answer.value
            }
        }
        return Outcome.Success(
            PurchaseVerification(
                productId = answers.firstOrNull()?.productId.orEmpty(),
                state = answers.lastOrNull()?.state.orEmpty(),
                crystalsCredited = answers.sumOf { it.crystalsCredited },
                balance = answers.lastOrNull { it.balance != null }?.balance,
                consume = answers.isNotEmpty() && answers.all { it.consume },
                entitled = answers.isNotEmpty() && answers.all { it.entitled },
            ),
        )
    }
}
