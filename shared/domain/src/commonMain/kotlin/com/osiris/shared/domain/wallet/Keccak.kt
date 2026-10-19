// The permutation is written in the specification's own numbers (5x5 lanes, byte shifts), which
// read more clearly than names for each; the test checks it against published vectors.
@file:Suppress("MagicNumber")

package com.osiris.shared.domain.wallet

/**
 * Keccak-256 as Ethereum uses it (original Keccak padding 0x01, not SHA3-256's 0x06). Needed only
 * for the EIP-55 address checksum, so it favours clarity over speed.
 */
internal object Keccak {
    private const val RATE_BYTES = 136
    private const val ROUNDS = 24
    private const val OUT_BYTES = 32

    private val ROUND_CONSTANTS = listOf(
        0x0000000000000001uL, 0x0000000000008082uL, 0x800000000000808AuL, 0x8000000080008000uL,
        0x000000000000808BuL, 0x0000000080000001uL, 0x8000000080008081uL, 0x8000000000008009uL,
        0x000000000000008AuL, 0x0000000000000088uL, 0x0000000080008009uL, 0x000000008000000AuL,
        0x000000008000808BuL, 0x800000000000008BuL, 0x8000000000008089uL, 0x8000000000008003uL,
        0x8000000000008002uL, 0x8000000000000080uL, 0x000000000000800AuL, 0x800000008000000AuL,
        0x8000000080008081uL, 0x8000000000008080uL, 0x0000000080000001uL, 0x8000000080008008uL,
    ).map(ULong::toLong).toLongArray()

    /** Rotation offsets, indexed x + 5y. */
    private val ROTATIONS = intArrayOf(
        0, 1, 62, 28, 27,
        36, 44, 6, 55, 20,
        3, 10, 43, 25, 39,
        41, 45, 15, 21, 8,
        18, 2, 61, 56, 14,
    )

    fun hash256(input: ByteArray): ByteArray {
        val padded = input.copyOf(((input.size / RATE_BYTES) + 1) * RATE_BYTES)
        padded[input.size] = (padded[input.size].toInt() xor 0x01).toByte()
        padded[padded.size - 1] = (padded[padded.size - 1].toInt() xor 0x80).toByte()
        val state = LongArray(25)
        for (block in padded.indices step RATE_BYTES) {
            for (i in 0 until RATE_BYTES / 8) state[i] = state[i] xor readLane(padded, block + i * 8)
            permute(state)
        }
        return ByteArray(OUT_BYTES) { i -> (state[i / 8] ushr (8 * (i % 8))).toByte() }
    }

    private fun readLane(bytes: ByteArray, offset: Int): Long {
        var lane = 0L
        for (b in 7 downTo 0) lane = (lane shl 8) or (bytes[offset + b].toLong() and 0xff)
        return lane
    }

    private fun permute(a: LongArray) {
        val c = LongArray(5)
        val b = LongArray(25)
        for (round in 0 until ROUNDS) {
            for (x in 0 until 5) c[x] = a[x] xor a[x + 5] xor a[x + 10] xor a[x + 15] xor a[x + 20]
            for (x in 0 until 5) {
                val d = c[(x + 4) % 5] xor c[(x + 1) % 5].rotateLeft(1)
                for (y in 0 until 25 step 5) a[x + y] = a[x + y] xor d
            }
            for (x in 0 until 5) {
                for (y in 0 until 5) {
                    b[y + 5 * ((2 * x + 3 * y) % 5)] = a[x + 5 * y].rotateLeft(ROTATIONS[x + 5 * y])
                }
            }
            for (y in 0 until 25 step 5) {
                for (x in 0 until 5) a[x + y] = b[x + y] xor (b[(x + 1) % 5 + y].inv() and b[(x + 2) % 5 + y])
            }
            a[0] = a[0] xor ROUND_CONSTANTS[round]
        }
    }
}
