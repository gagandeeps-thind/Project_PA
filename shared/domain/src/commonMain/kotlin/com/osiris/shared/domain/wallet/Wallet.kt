package com.osiris.shared.domain.wallet

import com.osiris.shared.domain.common.Format
import kotlin.math.abs
import kotlin.time.Instant

/** An amount in minor units (cents), so sums never pick up floating-point error. */
data class Money(val minor: Long, val currency: String) {
    /** `$12.50`, `-€3.00`, or `12.50 CHF` for currencies without a symbol here. */
    fun format(): String {
        val body = Format.fixed(abs(minor) / MINOR_PER_UNIT, 2)
        val sign = if (minor < 0) "-" else ""
        return SYMBOLS[currency]?.let { "$sign$it$body" } ?: "$sign$body $currency"
    }

    private companion object {
        const val MINOR_PER_UNIT = 100.0
        val SYMBOLS = mapOf("USD" to "$", "EUR" to "€", "GBP" to "£", "INR" to "₹")
    }
}

enum class Chain(val title: String) { ETHEREUM("Ethereum"), SOLANA("Solana") }

/**
 * A saved way to pay or be paid. Cards and bank accounts hold only what the payment provider
 * returns after its own secure sheet (brand, last four digits): the app never sees a card number.
 */
sealed interface PaymentMethod {
    val id: String
    val label: String

    data class Card(
        override val id: String,
        val brand: String,
        val last4: String,
        val expMonth: Int,
        val expYear: Int,
    ) : PaymentMethod {
        override val label: String get() = "$brand •••• $last4"
        val expiry: String get() = "${expMonth.toString().padStart(2, '0')}/${expYear.toString().takeLast(2)}"
    }

    data class BankAccount(override val id: String, val bankName: String, val last4: String) : PaymentMethod {
        override val label: String get() = "$bankName •••• $last4"
    }

    data class CryptoWallet(override val id: String, val chain: Chain, val address: String) : PaymentMethod {
        override val label: String get() = "${chain.title} ${address.take(6)}…${address.takeLast(4)}"
    }
}

enum class TransactionKind(val title: String) {
    TOP_UP("Top-up"),
    ENTRY_FEE("Entry fee"),
    PAYOUT("Payout"),
    WITHDRAWAL("Withdrawal"),
    REFUND("Refund"),
}

enum class TransactionStatus { PENDING, COMPLETED, FAILED }

/** One wallet movement; [amount] is negative when money leaves the wallet. */
data class WalletTransaction(
    val id: String,
    val kind: TransactionKind,
    val amount: Money,
    val at: Instant,
    val description: String,
    val status: TransactionStatus = TransactionStatus.COMPLETED,
)

data class WalletOverview(
    val balances: List<Money>,
    val methods: List<PaymentMethod>,
    val transactions: List<WalletTransaction>,
)

/** Checks wallet addresses before they are saved, so a typo cannot become a lost payout. */
object CryptoAddress {
    private val ETH = Regex("^0x[0-9a-fA-F]{40}$")
    private const val BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    private const val SOLANA_KEY_BYTES = 32
    private const val BYTE_BITS = 8
    private const val BYTE_MASK = 0xff
    private const val NIBBLE_BITS = 4
    private const val NIBBLE_MASK = 0xf

    /** EIP-55 upper-cases a hex letter when its hash nibble has the high bit set. */
    private const val UPPERCASE_FROM = 8

    /** The address to store, or null when it is not a valid address on [chain]. */
    fun normalize(chain: Chain, raw: String): String? {
        val address = raw.trim()
        return when (chain) {
            Chain.ETHEREUM -> address.takeIf { isEthereum(it) }?.let { checksummed(it.substring(2).lowercase()) }
            Chain.SOLANA -> address.takeIf { base58Decode(it)?.size == SOLANA_KEY_BYTES }
        }
    }

    /**
     * EIP-55: a single-case address carries no checksum and is accepted; a mixed-case one must
     * match its checksum exactly, which catches almost every mistyped character.
     */
    private fun isEthereum(address: String): Boolean {
        if (!ETH.matches(address)) return false
        val hex = address.substring(2)
        return hex == hex.lowercase() || hex == hex.uppercase() || address == checksummed(hex.lowercase())
    }

    private fun checksummed(lowerHex: String): String {
        val hash = Keccak.hash256(lowerHex.encodeToByteArray())
        val out = StringBuilder("0x")
        lowerHex.forEachIndexed { i, c ->
            val nibble = (hash[i / 2].toInt() shr (if (i % 2 == 0) NIBBLE_BITS else 0)) and NIBBLE_MASK
            out.append(if (c.isLetter() && nibble >= UPPERCASE_FROM) c.uppercaseChar() else c)
        }
        return out.toString()
    }

    /** Bitcoin-alphabet base58; null when empty or on any character outside the alphabet. */
    internal fun base58Decode(text: String): ByteArray? {
        if (text.isEmpty() || text.any { it !in BASE58 }) return null
        val bytes = ArrayList<Int>()
        for (ch in text) {
            var carry = BASE58.indexOf(ch)
            for (j in bytes.indices) {
                carry += bytes[j] * BASE58.length
                bytes[j] = carry and BYTE_MASK
                carry = carry shr BYTE_BITS
            }
            while (carry > 0) {
                bytes.add(carry and BYTE_MASK)
                carry = carry shr BYTE_BITS
            }
        }
        val leadingZeros = text.takeWhile { it == BASE58[0] }.length
        return ByteArray(leadingZeros) + bytes.reversed().map(Int::toByte).toByteArray()
    }
}
