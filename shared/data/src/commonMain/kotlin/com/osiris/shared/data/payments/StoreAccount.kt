package com.osiris.shared.data.payments

import io.ktor.util.hex
import io.ktor.util.sha1

/**
 * The account binding each store carries with a purchase, so the server can refuse a purchase made
 * for another player (409). Both are derived from the user id, which never reaches the store itself.
 * The server computes the same values (services/google_play.py, services/app_store.py).
 */
object StoreAccount {
    /** Play `obfuscatedAccountId`: lowercase hex SHA-256 of `osiris:<user id>`. */
    fun playObfuscatedAccountId(userId: Int): String = hex(Sha256.digest(seed(userId).encodeToByteArray()))

    /** StoreKit 2 `appAccountToken`: UUIDv5(NAMESPACE_URL, `osiris:<user id>`), lowercase. */
    @Suppress("MagicNumber") // RFC 4122 version and variant bits
    fun appStoreAccountToken(userId: Int): String {
        val b = sha1(hex(NAMESPACE_URL) + seed(userId).encodeToByteArray()).copyOf(16)
        b[6] = (b[6].toInt() and 0x0f or 0x50).toByte()
        b[8] = (b[8].toInt() and 0x3f or 0x80).toByte()
        val h = hex(b)
        return "${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}"
    }

    private fun seed(userId: Int) = "osiris:$userId"

    /** RFC 4122 namespace for URLs, 6ba7b811-9dad-11d1-80b4-00c04fd430c8. */
    private const val NAMESPACE_URL = "6ba7b8119dad11d180b400c04fd430c8"
}

/** FIPS 180-4 SHA-256. Ktor's common `Digest` is not available on iOS, so the shared code carries its own. */
@Suppress("MagicNumber")
internal object Sha256 {
    private val K = (
        "428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5 " +
            "d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174 " +
            "e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da " +
            "983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967 " +
            "27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85 " +
            "a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070 " +
            "19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3 " +
            "748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2"
        ).words()
    private val H0 = "6a09e667 bb67ae85 3c6ef372 a54ff53a 510e527f 9b05688c 1f83d9ab 5be0cd19".words()

    private fun String.words() = split(' ').map { it.toLong(16).toInt() }.toIntArray()

    fun digest(message: ByteArray): ByteArray {
        // Message, 0x80, zeros, then the bit length as a 64-bit big-endian number, in 64-byte blocks.
        val padded = message.copyOf((message.size + 72) / 64 * 64)
        padded[message.size] = 0x80.toByte()
        val bits = message.size.toLong() * 8
        for (i in 0 until 8) padded[padded.size - 1 - i] = (bits ushr (8 * i)).toByte()

        val h = H0.copyOf()
        val w = IntArray(64)
        for (block in padded.indices step 64) {
            for (t in 0 until 16) w[t] = padded.intAt(block + t * 4)
            for (t in 16 until 64) {
                val s0 = w[t - 15].rotateRight(7) xor w[t - 15].rotateRight(18) xor (w[t - 15] ushr 3)
                val s1 = w[t - 2].rotateRight(17) xor w[t - 2].rotateRight(19) xor (w[t - 2] ushr 10)
                w[t] = w[t - 16] + s0 + w[t - 7] + s1
            }
            compress(h, w)
        }
        return ByteArray(32) { i -> (h[i / 4] ushr (24 - 8 * (i % 4))).toByte() }
    }

    private fun compress(h: IntArray, w: IntArray) {
        var a = h[0]
        var b = h[1]
        var c = h[2]
        var d = h[3]
        var e = h[4]
        var f = h[5]
        var g = h[6]
        var hh = h[7]
        for (t in 0 until 64) {
            val t1 = hh + (e.rotateRight(6) xor e.rotateRight(11) xor e.rotateRight(25)) +
                ((e and f) xor (e.inv() and g)) + K[t] + w[t]
            val t2 = (a.rotateRight(2) xor a.rotateRight(13) xor a.rotateRight(22)) +
                ((a and b) xor (a and c) xor (b and c))
            hh = g
            g = f
            f = e
            e = d + t1
            d = c
            c = b
            b = a
            a = t1 + t2
        }
        h[0] += a
        h[1] += b
        h[2] += c
        h[3] += d
        h[4] += e
        h[5] += f
        h[6] += g
        h[7] += hh
    }

    private fun ByteArray.intAt(o: Int): Int =
        (this[o].toInt() and 0xff shl 24) or (this[o + 1].toInt() and 0xff shl 16) or
            (this[o + 2].toInt() and 0xff shl 8) or (this[o + 3].toInt() and 0xff)
}
