package com.osiris.shared.domain.model

import kotlin.time.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** A message from support on the live chat (`/api/v2/support/ws`). */
@Serializable
data class SupportMessage(
    val from: String,
    val text: String,
    @Serializable(with = ServerInstantSerializer::class) val at: Instant,
)

/** What the app sends on the live chat. */
@Serializable
data class SupportOutgoing(@SerialName("text") val text: String) {
    companion object {
        const val MAX_LENGTH = 1000
    }
}
