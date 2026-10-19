package com.osiris.shared.domain.exercise

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Accuracy evaluation of the rep engine under real-world distortions (port of
 * accuracy_eval_test.dart, report 16). Genuine sets are replayed at several pose frame rates,
 * landmark jitter levels, body sizes, phone roll angles and tempos; cheat sets must never count.
 * Run with `-Posiris.testOutput=true` to print the matrix.
 */
class AccuracyEvalTest {
    private val catalog = loadCatalog()

    private data class Condition(val fps: Int, val jitterPx: Double, val scale: Double, val rollDeg: Double, val tempo: Double) {
        override fun toString() = "${fps}fps j${jitterPx.toInt()} s$scale r${rollDeg.toInt()} t$tempo"
    }

    private class Movement(val cycleMs: Int, val pauseMs: Int, val reps: Int, val profile: (Double, Int) -> Map<String, Landmark>)

    private val genuine = linkedMapOf(
        "pushup" to Movement(1600, 300, 12) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0) },
        "squat" to Movement(2200, 300, 12) { p, _ ->
            sideBody(torsoDeg = -90 + swing(p, 0.0, 40.0), knee = swing(p, 175.0, 80.0), hip = swing(p, 175.0, 85.0))
        },
        "lunge" to Movement(2400, 300, 12) { p, leg ->
            val knee = swing(p, 172.0, 90.0)
            val hip = swing(p, 175.0, 100.0)
            if (leg % 2 == 0) sideBody(knee = knee, hip = hip, farKnee = 172.0, farHip = 175.0)
            else sideBody(knee = 172.0, hip = 175.0, farKnee = knee, farHip = hip)
        },
        "situp" to Movement(2400, 300, 12) { p, _ -> sideBody(thighDeg = -40.0, knee = 70.0, hip = swing(p, 140.0, 55.0)) },
        "jumping_jack" to Movement(900, 100, 20) { p, _ -> frontBody(arm = swing(p, 20.0, 165.0), spread = swing(p, 1.0, 2.2)) },
        "high_knees" to Movement(600, 60, 24) { p, i ->
            val lift = swing(p, 178.0, 95.0)
            val knee = swing(p, 178.0, 90.0)
            if (i % 2 == 0) sideBody(hip = lift, knee = knee, farHip = 178.0, farKnee = 178.0)
            else sideBody(hip = 178.0, knee = 178.0, farHip = lift, farKnee = knee)
        },
    )

    private val cheats: Map<String, List<Pair<String, Movement>>> = linkedMapOf(
        "pushup" to listOf(
            "half range" to Movement(1400, 300, 10) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 118.0), shoulder = 80.0) },
            "standing curls" to Movement(1600, 300, 10) { p, _ -> sideBody(torsoDeg = -90.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0) },
            "bouncing" to Movement(450, 0, 12) { p, _ -> sideBody(torsoDeg = 190.0, elbow = swing(p, 170.0, 80.0), shoulder = 80.0) },
        ),
        "squat" to listOf(
            "half range" to Movement(2000, 300, 10) { p, _ -> sideBody(knee = swing(p, 175.0, 125.0), hip = swing(p, 175.0, 130.0)) },
            "lying leg bends" to Movement(2200, 300, 10) { p, _ -> sideBody(torsoDeg = 180.0, knee = swing(p, 175.0, 80.0), hip = swing(p, 175.0, 95.0)) },
        ),
        "lunge" to listOf("half range" to Movement(2200, 300, 10) { p, _ -> sideBody(knee = swing(p, 172.0, 130.0)) }),
        "situp" to listOf(
            "half range" to Movement(2200, 300, 10) { p, _ -> sideBody(thighDeg = -40.0, knee = 70.0, hip = swing(p, 140.0, 95.0)) },
            "standing bends" to Movement(2400, 300, 10) { p, _ -> sideBody(thighDeg = 90.0, knee = 175.0, hip = swing(p, 140.0, 55.0)) },
        ),
        "jumping_jack" to listOf(
            "arms only" to Movement(900, 100, 15) { p, _ -> frontBody(arm = swing(p, 20.0, 165.0), spread = 1.0) },
            "half arms" to Movement(900, 100, 15) { p, _ -> frontBody(arm = swing(p, 20.0, 100.0), spread = swing(p, 1.0, 2.2)) },
        ),
        "high_knees" to listOf(
            "small lifts" to Movement(600, 60, 20) { p, _ -> sideBody(hip = swing(p, 178.0, 140.0), knee = swing(p, 178.0, 140.0)) },
            "lying knee pulls" to Movement(700, 60, 20) { p, _ -> sideBody(torsoDeg = 180.0, hip = swing(p, 178.0, 95.0), knee = swing(p, 178.0, 90.0)) },
        ),
    )

    /** Distance to the phone (scale about the frame centre), phone roll and landmark jitter. */
    private fun distort(lm: Map<String, Landmark>, c: Condition, rnd: DartRandom): Map<String, Landmark> {
        val cx = 200.0
        val cy = 250.0
        val r = c.rollDeg * PI / 180
        val cosR = cos(r)
        val sinR = sin(r)
        fun jitter() = (rnd.nextDouble() + rnd.nextDouble() - 1) * c.jitterPx
        return lm.mapValues { (_, v) ->
            val dx = (v.x - cx) * c.scale
            val dy = (v.y - cy) * c.scale
            val x = cx + dx * cosR - dy * sinR + jitter()
            val y = cy + dx * sinR + dy * cosR + jitter()
            Landmark(x, y, v.likelihood)
        }
    }

    private val swingRange = mapOf(
        "pushup" to (170.0 to 80.0), "squat" to (175.0 to 80.0), "lunge" to (172.0 to 90.0),
        "situp" to (140.0 to 55.0), "jumping_jack" to (20.0 to 165.0), "high_knees" to (178.0 to 95.0),
    )

    private fun fastestLegalCycleMs(key: String): Int {
        val (rest, peak) = swingRange.getValue(key)
        val threshold = catalog.byKey(key)!!.rest.threshold
        val f = ((threshold - rest) / (peak - rest)).coerceIn(0.0, 1.0)
        val share = 1 - 2 * acos(1 - 2 * f) / (2 * PI)
        val minRep = catalog.byKey(key)!!.minRepS * 1000
        return ceil(minRep * 1.15 / share / 0.85).toInt()
    }

    private fun render(m: Movement, c: Condition, seed: Int, cycleMs: Int? = null): List<PoseFrame> {
        val rnd = DartRandom(seed.toLong())
        val base = if (c.tempo == 0.0) cycleMs!! else m.cycleMs
        val scale = base.toDouble() / m.cycleMs
        return cycles(humanTempo(m.reps, base, seed = seed), fps = c.fps, pauseMs = floor(m.pauseMs * scale + 0.5).toInt()) { p, i ->
            distort(m.profile(p, i), c, rnd)
        }
    }

    /** The supported envelope: landmark jitter up to ~7% of torso length. */
    private fun inEnvelope(c: Condition) = c.jitterPx / c.scale <= 8.0

    private fun plankCredit(c: Condition, seed: Int): Double {
        val rnd = DartRandom(seed.toLong())
        val step = 1000 / c.fps
        val engine = RepEngine(catalog.byKey("plank")!!, catalog)
        var t = 0L
        while (t < 2000) {
            engine.addFrame(PoseFrame(t, distort(sideBody(torsoDeg = -90.0, hip = 90.0, knee = 178.0), c, rnd))); t += step
        }
        val start = t
        while (t < start + 30000) {
            engine.addFrame(PoseFrame(t, distort(sideBody(torsoDeg = 190.0, knee = 178.0, hip = 176.0, shoulder = 80.0, elbow = 90.0), c, rnd))); t += step
        }
        return engine.finish().holdS / 30.0
    }

    private val fpsLevels = listOf(30, 15, 10, 7, 5)
    private val jitterLevels = listOf(1.5, 4.0, 8.0)
    private val scaleLevels = listOf(0.5, 1.0, 1.3)
    private val rollLevels = listOf(-12.0, 0.0, 12.0)
    private val tempoLevels = listOf(1.0, 0.0)

    @Test
    fun genuineRepsAreCountedAtEverySupportedFrameRate() {
        val failures = mutableListOf<String>()
        val report = StringBuilder("Genuine reps counted (%) inside the envelope; columns: pose fps ${fpsLevels}\n")
        for ((key, m) in genuine) {
            val minFps = catalog.byKey(key)!!.minPoseFps
            val cells = mutableListOf<String>()
            for (fps in fpsLevels) {
                var performed = 0
                var counted = 0
                var seed = 0
                for (j in jitterLevels) for (s in scaleLevels) for (r in rollLevels) for (t in tempoLevels) {
                    val c = Condition(fps, j, s, r, t)
                    val sum = judge(catalog, key, render(m, c, ++seed, fastestLegalCycleMs(key)))
                    if (!inEnvelope(c)) continue
                    performed += m.reps
                    counted += sum.repsValid
                    if (fps < minFps) continue
                    if ("unsteady_tracking" in sum.reasons) failures += "$key $c: refused as unsteady inside the envelope"
                    if (sum.repsValid.toDouble() / m.reps < 0.80) failures += "$key $c: ${sum.repsValid}/${m.reps} ${sum.reasons}"
                }
                val share = counted.toDouble() / performed
                if (fps >= minFps && share < 0.95) failures += "$key at $fps fps: ${100 * share}%"
                cells += if (fps >= minFps) "%.1f".format(100 * share) else "·"
            }
            report.append(key.padEnd(14)).append(cells.joinToString(" ") { it.padStart(6) }).append('\n')
        }
        println(report)
        assertTrue(failures.isEmpty(), failures.joinToString("\n"))
    }

    @Test
    fun plankHoldsAreCreditedAtEverySupportedFrameRate() {
        val failures = mutableListOf<String>()
        for (fps in fpsLevels) {
            var sum = 0.0
            var n = 0
            for (j in jitterLevels) for (s in scaleLevels) for (r in rollLevels) sum += plankCredit(Condition(fps, j, s, r, 1.0), ++n)
            if (sum / n < 0.95) failures += "plank at $fps fps: ${100 * sum / n}%"
            println("plank $fps fps: ${"%.1f".format(100 * sum / n)}% credited")
        }
        assertTrue(failures.isEmpty(), failures.joinToString("\n"))
    }

    @Test
    fun cheatRepsAreNeverCounted() {
        val failures = mutableListOf<String>()
        for ((key, list) in cheats) for ((name, m) in list) {
            var seed = 1000
            for (fps in fpsLevels) for (j in jitterLevels) for (s in scaleLevels) for (r in rollLevels) {
                val c = Condition(fps, j, s, r, 1.0)
                val n = judge(catalog, key, render(m, c, ++seed)).repsValid
                if (n > 0) failures += "$key $name $c: $n counted"
            }
        }
        assertTrue(failures.isEmpty(), failures.joinToString("\n"))
    }
}
