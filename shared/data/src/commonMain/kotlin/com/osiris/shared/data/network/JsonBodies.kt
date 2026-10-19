package com.osiris.shared.data.network

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Small builder for request bodies; drops null values (the backend treats a sent null as a value). */
object JsonBodies {
    fun of(vararg pairs: Pair<String, Any?>): JsonObject =
        JsonObject(pairs.mapNotNull { (k, v) -> toElement(v)?.let { k to it } }.toMap())

    fun toElement(v: Any?): JsonElement? = when (v) {
        null -> null
        is JsonElement -> v
        is String -> JsonPrimitive(v)
        is Number -> JsonPrimitive(v)
        is Boolean -> JsonPrimitive(v)
        is Map<*, *> -> JsonObject(v.entries.mapNotNull { (k, x) -> toElement(x)?.let { k.toString() to it } }.toMap())
        is Iterable<*> -> JsonArray(v.map { toElement(it) ?: JsonNull })
        else -> JsonPrimitive(v.toString())
    }
}
