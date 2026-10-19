package com.osiris.shared.domain.exercise

import kotlin.test.Test
import kotlin.test.assertEquals

class DartRandomTest {
    /** Printed by `Random(seed).nextDouble()` on Dart SDK 3.13.5. */
    private val expected = mapOf(
        1L to listOf(0.5785012864412081, 0.25563430262583553, 0.9199665121717772, 0.9360953686036907),
        3L to listOf(0.3632060151900366, 0.06022772268535437, 0.06918274463971708, 0.6650418250603964),
        31L to listOf(0.0050380230712653296, 0.41422036777274795, 0.8333927187959348, 0.20940383881487878),
        1000L to listOf(0.225530844568134, 0.299522279596352, 0.9525368360472415, 0.39999657573955016),
    )

    @Test
    fun matchesTheDartVmSequence() {
        for ((seed, values) in expected) {
            val r = DartRandom(seed)
            assertEquals(values, List(4) { r.nextDouble() }, "seed $seed")
        }
    }
}
