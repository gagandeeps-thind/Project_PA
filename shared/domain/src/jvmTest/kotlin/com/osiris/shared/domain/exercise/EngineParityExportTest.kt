package com.osiris.shared.domain.exercise

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Writes a corpus of pose streams and this engine's verdict on each to `build/parity/`, so
 * `tools/parity/check_engine_parity.sh` can replay the same streams through the Dart engine and
 * prove both apps judge every set identically while the Flutter app is still in service.
 */
class EngineParityExportTest {
    private val catalog = loadCatalog()

    private fun corpus(): List<Pair<String, PoseRecording>> {
        val out = mutableListOf<Pair<String, PoseRecording>>()
        val at = Instant.parse("2026-10-19T00:00:00Z")
        fun add(name: String, key: String, frames: List<PoseFrame>) {
            out += name to PoseRecording(key, catalog.rulesVersion, at, "synthetic", frames, labelReps = null, note = name)
        }
        var seed = 0
        for (fps in listOf(30, 10, 5)) for (px in listOf(1.5, 8.0, 16.0)) {
            seed++
            fun n() = Noise(seed, px)
            val pn = n()
            add("pushup full ${fps}fps ${px}px", "pushup", cycles(humanTempo(10, 1600, seed), fps = fps) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0, noise = pn) })
            val hn = n()
            add("pushup half ${fps}fps ${px}px", "pushup", cycles(humanTempo(8, 1400, seed), fps = fps) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 118.0), shoulder = 80.0, noise = hn) })
            val sn = n()
            add("squat ${fps}fps ${px}px", "squat", cycles(humanTempo(10, 2200, seed), fps = fps) { p, _ -> sideBody(torsoDeg = -90 + swing(p, 0.0, 40.0), knee = swing(p, 175.0, 80.0), hip = swing(p, 175.0, 85.0), noise = sn) })
            val ln = n()
            add("lunge ${fps}fps ${px}px", "lunge", cycles(humanTempo(10, 2400, seed), fps = fps) { p, leg ->
                val knee = swing(p, 172.0, 90.0); val hip = swing(p, 175.0, 100.0)
                if (leg % 2 == 0) sideBody(knee = knee, hip = hip, farKnee = 172.0, farHip = 175.0, noise = ln) else sideBody(knee = 172.0, hip = 175.0, farKnee = knee, farHip = hip, noise = ln)
            })
            val un = n()
            add("situp ${fps}fps ${px}px", "situp", cycles(humanTempo(10, 2400, seed), fps = fps) { p, _ -> sideBody(thighDeg = -40.0, knee = 70.0, hip = swing(p, 140.0, 55.0), noise = un) })
            val jn = n()
            add("jumping jack ${fps}fps ${px}px", "jumping_jack", cycles(humanTempo(15, 900, seed), fps = fps, pauseMs = 100) { p, _ -> frontBody(arm = swing(p, 20.0, 165.0), spread = swing(p, 1.0, 2.2), noise = jn) })
            val kn = n()
            add("high knees ${fps}fps ${px}px", "high_knees", cycles(humanTempo(16, 600, seed), fps = fps, pauseMs = 60) { p, i ->
                val lift = swing(p, 178.0, 95.0); val knee = swing(p, 178.0, 90.0)
                if (i % 2 == 0) sideBody(hip = lift, knee = knee, farHip = 178.0, farKnee = 178.0, noise = kn) else sideBody(hip = 178.0, knee = 178.0, farHip = lift, farKnee = knee, noise = kn)
            })
            val step = 1000L / fps
            val plankNoise = n()
            val plank = (0L until 2000L step step).map { PoseFrame(it, sideBody(torsoDeg = -90.0, hip = 90.0, knee = 178.0, noise = plankNoise)) } +
                (2000L until 32000L step step).map { PoseFrame(it, sideBody(torsoDeg = 190.0, knee = 178.0, hip = 176.0, shoulder = 80.0, elbow = 90.0, noise = plankNoise)) }
            add("plank ${fps}fps ${px}px", "plank", plank)
        }
        return out
    }

    @Test
    fun exportCorpusAndKotlinVerdicts() {
        val dir = File("build/parity/inputs").apply { mkdirs() }
        val results = buildJsonArray {
            corpus().forEachIndexed { i, (name, rec) ->
                val file = File(dir, "case_%03d.json".format(i))
                file.writeText(rec.toJson())
                // Judge the stored (0.1 px rounded) frames, exactly what the Dart side will read.
                val s = judge(catalog, rec.exerciseKey, PoseRecording.parse(file.readText()).frames)
                add(buildJsonObject {
                    put("file", file.name)
                    put("name", name)
                    put("reps_valid", s.repsValid)
                    put("reps_attempted", s.repsAttempted)
                    put("hold_s", s.holdS)
                    put("form_score", s.formScore)
                    put("verdict", s.verdict.wire)
                    put("reasons", JsonArray(s.reasons.map(::JsonPrimitive)))
                    put("rep_durations_ms", JsonArray(s.reps.map { JsonPrimitive(it.durationMs) }))
                })
            }
        }
        File("build/parity/kotlin_results.json").writeText(Json.encodeToString(JsonArray.serializer(), results))
        assertTrue(results.size >= 72)
        println("PARITY exported ${results.size} cases; verdicts ${results.groupingBy { (it as JsonObject)["verdict"].toString() }.eachCount()}")
    }
}
