package com.osiris.shared.domain.model

import com.osiris.shared.domain.run.LatLng
import kotlin.time.Instant
import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

/**
 * Server timestamps. The backend sends naive UTC (`2026-10-19T10:00:00`); those are read as UTC.
 * Timestamps with `Z` or an offset are read as given.
 */
object ServerInstantSerializer : KSerializer<Instant> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("ServerInstant", PrimitiveKind.STRING)

    private val zoned = Regex("""(Z|[+-]\d\d:\d\d)$""")

    fun parse(s: String): Instant = Instant.parse(if (zoned.containsMatchIn(s)) s else "${s}Z")

    override fun deserialize(decoder: Decoder): Instant = parse(decoder.decodeString())

    override fun serialize(encoder: Encoder, value: Instant) = encoder.encodeString(value.toString())
}

/** Routes arrive as `[[lat, lng], ...]`. */
object RouteSerializer : KSerializer<List<LatLng>> {
    override val descriptor: SerialDescriptor = JsonArray.serializer().descriptor

    override fun deserialize(decoder: Decoder): List<LatLng> {
        val json = (decoder as JsonDecoder).decodeJsonElement()
        return json.jsonArray.map { p ->
            val a = p.jsonArray
            LatLng(a[0].jsonPrimitive.double, a[1].jsonPrimitive.double)
        }
    }

    override fun serialize(encoder: Encoder, value: List<LatLng>) {
        (encoder as JsonEncoder).encodeJsonElement(
            JsonArray(value.map { JsonArray(listOf(JsonPrimitive(it.lat), JsonPrimitive(it.lng))) }),
        )
    }
}
