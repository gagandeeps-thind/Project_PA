package com.osiris.shared.domain.wallet

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The server's answer to a store purchase (`POST /api/v2/payments/google-play/verify` and
 * `/api/v2/payments/app-store/verify`, same shape). Every figure is the server's: the app shows
 * [crystalsCredited] and [balance], never its own catalog amounts.
 *
 * @property entitled the purchase currently grants its product.
 * @property consume Play: call consumeAsync now so the pack can be bought again.
 * @property crystalsCredited crystals granted by this call (quantity included; 0 on a repeat).
 * @property balance the player's crystal balance after the call.
 */
@Serializable
data class PurchaseVerification(
    @SerialName("product_id") val productId: String = "",
    val state: String = "",
    @SerialName("crystals_credited") val crystalsCredited: Int = 0,
    val balance: Int? = null,
    val consume: Boolean = false,
    val entitled: Boolean = false,
)

/** `GET /api/v2/payments/entitlements`: what the player's verified purchases, from either store, unlock now. */
@Serializable
data class StoreEntitlements(
    @SerialName("osiris_pass") val osirisPass: Boolean = false,
    @SerialName("osiris_pass_product_id") val osirisPassProductId: String? = null,
    @SerialName("osiris_pass_state") val osirisPassState: String? = null,
    @SerialName("founder_pack") val founderPack: Boolean = false,
)
