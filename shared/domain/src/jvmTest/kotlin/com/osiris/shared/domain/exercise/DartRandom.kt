package com.osiris.shared.domain.exercise

/**
 * Bit-exact port of the Dart VM's `Random(seed)` (multiply-with-carry, base 2^32, seeded with
 * Thomas Wang's 64-bit mix and cranked four times). The synthetic test sets use it so the Kotlin
 * tests feed the engine exactly the frames the Dart tests did; `DartRandomTest` pins it to values
 * printed by the Dart SDK.
 */
class DartRandom(seed: Long) {
    private var lo: Long
    private var hi: Long

    init {
        var s = mix64(seed)
        if (s == 0L) s = 0x5A17
        lo = s and MASK_32
        hi = s ushr 32
        repeat(4) { nextState() }
    }

    private fun nextState() {
        // state = A * lo + hi, as an unsigned 64-bit value.
        val state = A * lo + hi
        lo = state and MASK_32
        hi = state ushr 32
    }

    fun nextInt(max: Int): Int {
        require(max > 0)
        if (max and -max == max) {
            nextState()
            return (lo and (max - 1).toLong()).toInt()
        }
        var rnd32: Long
        var result: Long
        do {
            nextState()
            rnd32 = lo
            result = rnd32 % max
        } while (rnd32 - result + max > POW2_32)
        return result.toInt()
    }

    fun nextDouble(): Double = (nextInt(1 shl 26) * POW2_27_D + nextInt(1 shl 27)) / POW2_53_D

    private companion object {
        const val A = 0xffffda61L
        const val MASK_32 = 0xffffffffL
        const val POW2_32 = 1L shl 32
        const val POW2_27_D = (1L shl 27).toDouble()
        const val POW2_53_D = (1L shl 53).toDouble()

        fun mix64(input: Long): Long {
            var n = input
            n = n.inv() + (n shl 21)
            n = n xor (n ushr 24)
            n *= 265
            n = n xor (n ushr 14)
            n *= 21
            n = n xor (n ushr 28)
            n += n shl 31
            return n
        }
    }
}
