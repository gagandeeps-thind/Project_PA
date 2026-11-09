package com.osiris.shared.domain.wallet

import kotlinx.serialization.Serializable

/** `POST /api/v2/payments/google-play/verify`: [entitled] means the server granted the product. */
@Serializable
data class GooglePlayVerification(val entitled: Boolean = false)
