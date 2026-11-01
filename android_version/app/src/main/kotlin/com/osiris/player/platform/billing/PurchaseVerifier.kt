package com.osiris.player.platform.billing

import java.security.GeneralSecurityException
import java.security.KeyFactory
import java.security.PublicKey
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * Contract for verifying the authenticity of a purchase returned by Google Play Billing
 * before granting entitlements or acknowledging/consuming the token.
 *
 * Implementations may verify the Play Store RSA signature locally, forward the purchase token
 * to a backend verification endpoint (Google Play Developer API `purchases.products.get` /
 * `purchases.subscriptionsv2.get`), or compose both.
 */
fun interface PurchaseVerifier {
    suspend fun verify(
        packageName: String,
        signedData: String,
        signature: String,
        purchaseToken: String,
        productIds: List<String>,
    ): Boolean
}

/**
 * Verifies Google Play purchase receipts using:
 * 1. Structural JSON integrity checks (`packageName`, `purchaseToken`, `productId`, and `purchaseState`).
 * 2. RSA cryptographic signature verification (`SHA1withRSA` / `SHA256withRSA`) against the app's
 *    Base64-encoded Google Play licensing public key when configured via `BuildConfig.PLAY_BILLING_PUBLIC_KEY`.
 * 3. An optional server-side [remoteVerifier] delegate when backend receipt verification is enabled.
 */
class PlaySignaturePurchaseVerifier(
    private val base64PublicKey: String = "",
    private val remoteVerifier: PurchaseVerifier? = null,
) : PurchaseVerifier {

    private val json = Json { ignoreUnknownKeys = true }

    override suspend fun verify(
        packageName: String,
        signedData: String,
        signature: String,
        purchaseToken: String,
        productIds: List<String>,
    ): Boolean {
        val basicsValid = packageName.isNotBlank() &&
            signedData.isNotBlank() &&
            purchaseToken.isNotBlank() &&
            productIds.isNotEmpty() &&
            verifyJsonPayload(packageName, signedData, purchaseToken, productIds)

        val cryptoValid = basicsValid && verifySignatureIfConfigured(signedData, signature)
        return if (!cryptoValid) {
            false
        } else {
            remoteVerifier?.verify(packageName, signedData, signature, purchaseToken, productIds) ?: true
        }
    }

    private fun verifyJsonPayload(
        expectedPackageName: String,
        signedData: String,
        expectedPurchaseToken: String,
        expectedProductIds: List<String>,
    ): Boolean {
        val root = parseJsonObject(signedData) ?: return false
        val pkg = root["packageName"]?.jsonPrimitive?.content
        val token = root["purchaseToken"]?.jsonPrimitive?.content
        // In Google Play's signed JSON payload, purchaseState == 0 denotes PURCHASED (1 = CANCELED, 2 = PENDING).
        val purchaseState = root["purchaseState"]?.jsonPrimitive?.intOrNull ?: 0
        val singleProductId = root["productId"]?.jsonPrimitive?.content
        val productMatches = singleProductId == null || singleProductId in expectedProductIds

        return pkg == expectedPackageName &&
            token == expectedPurchaseToken &&
            purchaseState == PLAY_JSON_PURCHASED_STATE &&
            productMatches
    }

    private fun parseJsonObject(raw: String): JsonObject? = try {
        json.parseToJsonElement(raw) as? JsonObject
    } catch (_: IllegalArgumentException) {
        null
    }

    private fun verifySignatureIfConfigured(signedData: String, signature: String): Boolean {
        val keyText = base64PublicKey.trim()
        val publicKey = if (keyText.isNotEmpty() && signature.isNotBlank()) decodePublicKey(keyText) else null
        return when {
            keyText.isEmpty() -> true
            publicKey == null -> false
            else -> verifyWithAlgorithm(publicKey, signedData, signature, SHA1_WITH_RSA) ||
                verifyWithAlgorithm(publicKey, signedData, signature, SHA256_WITH_RSA)
        }
    }

    private fun decodePublicKey(encodedKey: String): PublicKey? = try {
        val decodedBytes = Base64.getDecoder().decode(encodedKey)
        val keyFactory = KeyFactory.getInstance(KEY_FACTORY_RSA)
        keyFactory.generatePublic(X509EncodedKeySpec(decodedBytes))
    } catch (_: IllegalArgumentException) {
        null
    } catch (_: GeneralSecurityException) {
        null
    }

    private fun verifyWithAlgorithm(
        publicKey: PublicKey,
        signedData: String,
        base64Signature: String,
        algorithm: String,
    ): Boolean = try {
        val signatureBytes = Base64.getDecoder().decode(base64Signature)
        val verifier = Signature.getInstance(algorithm)
        verifier.initVerify(publicKey)
        verifier.update(signedData.toByteArray(Charsets.UTF_8))
        verifier.verify(signatureBytes)
    } catch (_: IllegalArgumentException) {
        false
    } catch (_: GeneralSecurityException) {
        false
    }

    companion object {
        private const val KEY_FACTORY_RSA = "RSA"
        private const val SHA1_WITH_RSA = "SHA1withRSA"
        private const val SHA256_WITH_RSA = "SHA256withRSA"
        private const val PLAY_JSON_PURCHASED_STATE = 0
    }
}
