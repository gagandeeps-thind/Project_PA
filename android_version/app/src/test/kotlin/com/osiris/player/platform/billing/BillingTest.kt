package com.osiris.player.platform.billing

import com.android.billingclient.api.BillingClient.BillingResponseCode
import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.repository.PaymentsRepository
import com.osiris.shared.domain.wallet.GooglePlayVerification
import java.security.KeyPairGenerator
import java.security.Signature
import java.util.Base64
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BillingTest {

    private fun server(vararg answers: Pair<String, Outcome<GooglePlayVerification>>) = ServerPurchaseVerifier(
        object : PaymentsRepository {
            override suspend fun verifyGooglePlay(productId: String, purchaseToken: String) = answers.toMap().getValue(productId)
        },
    )

    private suspend fun ServerPurchaseVerifier.check(vararg products: String) = verify("p", "{}", "s", "token", products.toList())

    @Test
    fun serverVerifierGrantsOnlyWhenEveryProductIsEntitled() = runTest {
        val yes = Outcome.Success(GooglePlayVerification(entitled = true))
        val no = Outcome.Success(GooglePlayVerification(entitled = false))
        assertTrue(server("a" to yes).check("a"))
        assertFalse(server("a" to yes, "b" to no).check("a", "b"))
    }

    @Test
    fun serverVerifierKeepsThePurchaseWhenTheServerCannotAnswer() = runTest {
        assertFalse(server("a" to Outcome.Failure(AppError.Offline())).check("a"))
    }

    @Test
    fun catalogClassifiesConsumablesNonConsumablesAndSubscriptions() {
        assertEquals(
            ProductKind.CONSUMABLE_INAPP,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.PRODUCT_CRYSTALS_STARTER),
        )
        assertEquals(
            ProductKind.CONSUMABLE_INAPP,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.PRODUCT_CRYSTALS_ADVENTURER),
        )
        assertEquals(
            ProductKind.CONSUMABLE_INAPP,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.PRODUCT_CRYSTALS_CHAMPION),
        )
        assertEquals(
            ProductKind.NON_CONSUMABLE_INAPP,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.PRODUCT_FOUNDER_PACK),
        )
        assertEquals(
            ProductKind.SUBSCRIPTION,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.SUB_OSIRIS_PASS_MONTHLY),
        )
        assertEquals(
            ProductKind.SUBSCRIPTION,
            PlayBillingCatalog.kindOf(PlayBillingCatalog.SUB_OSIRIS_PASS_ANNUAL),
        )
        assertTrue(PlayBillingCatalog.isConsumable(PlayBillingCatalog.PRODUCT_CRYSTALS_STARTER))
        assertFalse(PlayBillingCatalog.isConsumable(PlayBillingCatalog.PRODUCT_FOUNDER_PACK))
        assertFalse(PlayBillingCatalog.isConsumable(PlayBillingCatalog.SUB_OSIRIS_PASS_MONTHLY))
        assertEquals(500, PlayBillingCatalog.crystalsForProduct(PlayBillingCatalog.PRODUCT_CRYSTALS_STARTER))
        assertEquals(1200, PlayBillingCatalog.crystalsForProduct(PlayBillingCatalog.PRODUCT_CRYSTALS_ADVENTURER))
        assertEquals(2600, PlayBillingCatalog.crystalsForProduct(PlayBillingCatalog.PRODUCT_CRYSTALS_CHAMPION))
        assertEquals(0, PlayBillingCatalog.crystalsForProduct(PlayBillingCatalog.SUB_OSIRIS_PASS_MONTHLY))
    }

    @Test
    fun errorMapperProducesActionableFeedbackForStandardCodes() {
        val canceled = BillingErrorMapper.fromResponseCode(BillingResponseCode.USER_CANCELED)
        assertEquals(BillingErrorCode.USER_CANCELED, canceled.code)
        assertFalse(canceled.isError)
        assertTrue(canceled.userMessage.contains("not charged"))

        val owned = BillingErrorMapper.fromResponseCode(BillingResponseCode.ITEM_ALREADY_OWNED)
        assertEquals(BillingErrorCode.ITEM_ALREADY_OWNED, owned.code)
        assertTrue(owned.isError)
        assertTrue(owned.userMessage.contains("already own"))

        val unavailable = BillingErrorMapper.fromResponseCode(BillingResponseCode.SERVICE_UNAVAILABLE)
        assertEquals(BillingErrorCode.SERVICE_UNAVAILABLE, unavailable.code)
        assertTrue(unavailable.isError)
        assertTrue(BillingErrorMapper.isRetriable(BillingResponseCode.SERVICE_UNAVAILABLE))

        val devError = BillingErrorMapper.fromResponseCode(BillingResponseCode.DEVELOPER_ERROR)
        assertEquals(BillingErrorCode.DEVELOPER_ERROR, devError.code)
        assertTrue(devError.isError)
        assertFalse(BillingErrorMapper.isRetriable(BillingResponseCode.DEVELOPER_ERROR))
    }

    @Test
    fun exponentialBackoffDoublesAndCapsAtMaxDelay() {
        assertEquals(1_000L, BillingErrorMapper.exponentialBackoffDelayMs(0))
        assertEquals(2_000L, BillingErrorMapper.exponentialBackoffDelayMs(1))
        assertEquals(4_000L, BillingErrorMapper.exponentialBackoffDelayMs(2))
        assertEquals(8_000L, BillingErrorMapper.exponentialBackoffDelayMs(3))
        assertEquals(16_000L, BillingErrorMapper.exponentialBackoffDelayMs(4))
        assertEquals(60_000L, BillingErrorMapper.exponentialBackoffDelayMs(8))
    }

    @Test
    fun subscriptionStatusTransitionsBetweenNoneActiveGracePeriodAndExpired() {
        val none = BillingErrorMapper.resolveSubscriptionStatus(
            activeSubscriptions = emptyList(),
            hadPreviousSubscription = false,
            inGracePeriod = false,
        )
        assertEquals(SubscriptionStatus.NONE, none)

        val verifiedRecord = BillingPurchaseRecord(
            orderId = "GPA.1234-5678-9012-34567",
            productIds = listOf(PlayBillingCatalog.SUB_OSIRIS_PASS_MONTHLY),
            purchaseToken = "tok_sub_1",
            purchaseTimeMillis = 1_700_000_000_000L,
            isAcknowledged = true,
            isAutoRenewing = true,
            status = PurchaseEntitlementStatus.VERIFIED_AND_GRANTED,
        )
        val active = BillingErrorMapper.resolveSubscriptionStatus(
            activeSubscriptions = listOf(verifiedRecord),
            hadPreviousSubscription = true,
            inGracePeriod = false,
        )
        assertEquals(SubscriptionStatus.ACTIVE, active)

        val grace = BillingErrorMapper.resolveSubscriptionStatus(
            activeSubscriptions = listOf(verifiedRecord),
            hadPreviousSubscription = true,
            inGracePeriod = true,
        )
        assertEquals(SubscriptionStatus.IN_GRACE_PERIOD, grace)

        val expired = BillingErrorMapper.resolveSubscriptionStatus(
            activeSubscriptions = emptyList(),
            hadPreviousSubscription = true,
            inGracePeriod = false,
        )
        assertEquals(SubscriptionStatus.EXPIRED, expired)
    }

    @Test
    fun signatureVerifierValidatesRsaSignatureAndRejectsTampering() = runTest {
        val keyPairGen = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }
        val keyPair = keyPairGen.generateKeyPair()
        val base64PublicKey = Base64.getEncoder().encodeToString(keyPair.public.encoded)

        val payload = """
            {
              "orderId": "GPA.3311-2233-4455-66778",
              "packageName": "com.osiris.player",
              "productId": "osiris_crystals_starter",
              "purchaseTime": 1730000000000,
              "purchaseState": 0,
              "purchaseToken": "token_abc_123"
            }
        """.trimIndent()

        val signer = Signature.getInstance("SHA256withRSA").apply {
            initSign(keyPair.private)
            update(payload.toByteArray(Charsets.UTF_8))
        }
        val validSignature = Base64.getEncoder().encodeToString(signer.sign())

        val verifier = PlaySignaturePurchaseVerifier(base64PublicKey = base64PublicKey)
        assertTrue(
            verifier.verify(
                packageName = "com.osiris.player",
                signedData = payload,
                signature = validSignature,
                purchaseToken = "token_abc_123",
                productIds = listOf(PlayBillingCatalog.PRODUCT_CRYSTALS_STARTER),
            ),
        )

        // Tampered package name must fail.
        assertFalse(
            verifier.verify(
                packageName = "com.evil.clone",
                signedData = payload,
                signature = validSignature,
                purchaseToken = "token_abc_123",
                productIds = listOf(PlayBillingCatalog.PRODUCT_CRYSTALS_STARTER),
            ),
        )

        // Tampered payload with original signature must fail cryptographic check.
        val tamperedPayload = payload.replace("osiris_crystals_starter", "osiris_crystals_champion")
        assertFalse(
            verifier.verify(
                packageName = "com.osiris.player",
                signedData = tamperedPayload,
                signature = validSignature,
                purchaseToken = "token_abc_123",
                productIds = listOf(PlayBillingCatalog.PRODUCT_CRYSTALS_CHAMPION),
            ),
        )
    }
}

