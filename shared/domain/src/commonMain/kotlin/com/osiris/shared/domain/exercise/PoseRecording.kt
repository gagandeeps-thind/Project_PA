package com.osiris.shared.domain.exercise

import kotlin.time.Instant
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put

/**
 * Landmark recording for device QA (format `osiris-pose-v1`, shared with the Flutter app; see
 * `Osiris_customer/test/exercise/recordings/README.md`). Only joint positions and their
 * confidence are saved, never images. Builds without [com.osiris.shared.core.config.FeatureFlags.poseRecording]
 * never record.
 */
data class PoseRecording(
    val exerciseKey: String,
    val rulesVersion: String,
    val recordedAt: Instant,
    /** `device` or `synthetic`. */
    val source: String,
    val frames: List<PoseFrame>,
    /** Reps that should count, as judged by the tester. */
    val labelReps: Int? = null,
    /** Seconds of good hold, for plank. */
    val labelHoldS: Double? = null,
    val note: String? = null,
) {
    fun toJson(): String = Json.encodeToString(JsonObject.serializer(), buildJsonObject {
        put("format", FORMAT)
        put("exercise_key", exerciseKey)
        put("rules_version", rulesVersion)
        put("recorded_at", recordedAt.toString())
        put("source", source)
        put("label_reps", labelReps)
        put("label_hold_s", labelHoldS)
        put("note", note)
        put("frames", buildJsonArray {
            for (f in frames) {
                add(buildJsonObject {
                    put("t", f.tMs)
                    put("l", buildJsonObject {
                        for ((k, lm) in f.landmarks) {
                            put(k, buildJsonArray {
                                add(JsonPrimitive(roundHalfUp(lm.x, 1)))
                                add(JsonPrimitive(roundHalfUp(lm.y, 1)))
                                add(JsonPrimitive(roundHalfUp(lm.likelihood, 2)))
                            })
                        }
                    })
                })
            }
        })
    })

    companion object {
        const val FORMAT = "osiris-pose-v1"

        /** Throws [IllegalArgumentException] for another format or a malformed file. */
        fun parse(source: String): PoseRecording {
            val j = Json.parseToJsonElement(source).jsonObject
            val format = j["format"]?.jsonPrimitive?.content
            require(format == FORMAT) { "Unsupported pose recording format: $format" }
            fun str(key: String) = requireNotNull(j[key]?.jsonPrimitive?.content) { "missing '$key'" }
            fun optStr(key: String) = j[key]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content
            return PoseRecording(
                exerciseKey = str("exercise_key"),
                rulesVersion = str("rules_version"),
                recordedAt = Instant.parse(str("recorded_at")),
                source = str("source"),
                labelReps = j["label_reps"]?.jsonPrimitive?.intOrNull,
                labelHoldS = j["label_hold_s"]?.jsonPrimitive?.doubleOrNull,
                note = optStr("note"),
                frames = (j["frames"] as? JsonArray ?: JsonArray(emptyList())).map { raw ->
                    val f = raw.jsonObject
                    PoseFrame(
                        f.getValue("t").jsonPrimitive.long,
                        f.getValue("l").jsonObject.mapValues { (_, v) ->
                            val a = v.jsonArray
                            Landmark(a[0].jsonPrimitive.double, a[1].jsonPrimitive.double, a[2].jsonPrimitive.double)
                        },
                    )
                },
            )
        }
    }
}

/** Collects a set's frames while recording is on. Capped at ten minutes of 30 fps tracking. */
class PoseRecorder {
    private val buffer = mutableListOf<PoseFrame>()

    val frames: List<PoseFrame> get() = buffer
    val full: Boolean get() = buffer.size >= MAX_FRAMES

    fun add(f: PoseFrame) {
        if (!full) buffer += f
    }

    fun finish(
        exerciseKey: String,
        rulesVersion: String,
        recordedAt: Instant,
        labelReps: Int? = null,
        labelHoldS: Double? = null,
        note: String? = null,
    ): PoseRecording = PoseRecording(
        exerciseKey = exerciseKey,
        rulesVersion = rulesVersion,
        recordedAt = recordedAt,
        source = "device",
        frames = buffer.toList(),
        labelReps = labelReps,
        labelHoldS = labelHoldS,
        note = note,
    )

    companion object {
        const val MAX_FRAMES = 30 * 60 * 10
    }
}
