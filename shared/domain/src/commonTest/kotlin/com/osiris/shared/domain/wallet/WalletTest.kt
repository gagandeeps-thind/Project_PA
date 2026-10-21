package com.osiris.shared.domain.wallet

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class WalletTest {
    @Test
    fun keccakMatchesEthereumVectors() {
        assertEquals(
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
            Keccak.hash256(ByteArray(0)).toHex(),
        )
        assertEquals(
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45",
            Keccak.hash256("abc".encodeToByteArray()).toHex(),
        )
        // Crosses the 136-byte block boundary.
        assertEquals(64, Keccak.hash256(ByteArray(200) { 1 }).toHex().length)
    }

    @Test
    fun ethereumAddressesFollowEip55() {
        val good = "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"
        assertEquals(good, CryptoAddress.normalize(Chain.ETHEREUM, good))
        assertEquals(good, CryptoAddress.normalize(Chain.ETHEREUM, " ${good.lowercase()} "))
        assertNull(CryptoAddress.normalize(Chain.ETHEREUM, "0xFB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"))
        assertNull(CryptoAddress.normalize(Chain.ETHEREUM, "0xfb6916095ca1df60bb79ce92ce3ea74c37c5d35"))
        assertNull(CryptoAddress.normalize(Chain.ETHEREUM, "fb6916095ca1df60bb79ce92ce3ea74c37c5d3590x"))
    }

    @Test
    fun solanaAddressesDecodeToThirtyTwoBytes() {
        assertEquals(
            "So11111111111111111111111111111111111111112",
            CryptoAddress.normalize(Chain.SOLANA, "So11111111111111111111111111111111111111112"),
        )
        assertEquals(32, CryptoAddress.base58Decode("11111111111111111111111111111111")?.size)
        assertNull(CryptoAddress.normalize(Chain.SOLANA, "So1111111111111111111111111111111111111111O"))
        assertNull(CryptoAddress.normalize(Chain.SOLANA, "abc"))
    }

    @Test
    fun moneyFormatsWithoutFloatDrift() {
        assertEquals("$0.30", Money(30, "USD").format())
        assertEquals("-€3.05", Money(-305, "EUR").format())
        assertEquals("12.50 CHF", Money(1250, "CHF").format())
    }

    private fun ByteArray.toHex() = joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
}
