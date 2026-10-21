package com.osiris.shared.data.wallet

import com.osiris.shared.core.error.AppError
import com.osiris.shared.core.error.Outcome
import com.osiris.shared.core.error.outcomeOf
import com.osiris.shared.domain.repository.WalletRepository
import com.osiris.shared.domain.wallet.Chain
import com.osiris.shared.domain.wallet.CryptoAddress
import com.osiris.shared.domain.wallet.Money
import com.osiris.shared.domain.wallet.PaymentMethod
import com.osiris.shared.domain.wallet.TransactionKind
import com.osiris.shared.domain.wallet.TransactionStatus
import com.osiris.shared.domain.wallet.TransactionStatus.COMPLETED
import com.osiris.shared.domain.wallet.WalletOverview
import com.osiris.shared.domain.wallet.WalletTransaction
import kotlin.time.Clock
import kotlin.time.Duration
import kotlin.time.Duration.Companion.days
import kotlin.time.Duration.Companion.hours
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * In-memory wallet for demo builds (`features.walletDemo`). Nothing leaves the phone and nothing
 * touches the crystal ledger. "Adding a card" stands in for the provider's sheet by returning
 * Stripe's public test card, the same shape a real adapter gets back.
 */
class MockWalletRepository(private val clock: Clock = Clock.System) : WalletRepository {
    override val isDemo: Boolean = true

    private val lock = Mutex()
    private var nextId = 1
    private val methods = mutableListOf<PaymentMethod>(
        PaymentMethod.Card(id(), "Visa", "4242", expMonth = 12, expYear = 2030),
    )
    private val transactions: List<WalletTransaction> = seed()

    override suspend fun overview(): Outcome<WalletOverview> = lock.withLock {
        Outcome.Success(WalletOverview(balances(), methods.toList(), transactions.sortedByDescending { it.at }))
    }

    override suspend fun addCard(): Outcome<PaymentMethod.Card> = save {
        PaymentMethod.Card(id(), "Visa", "4242", expMonth = 12, expYear = 2030)
    }

    override suspend fun linkBank(): Outcome<PaymentMethod.BankAccount> = save {
        PaymentMethod.BankAccount(id(), "Test Bank", "6789")
    }

    override suspend fun addCryptoWallet(chain: Chain, address: String): Outcome<PaymentMethod.CryptoWallet> = save {
        val normalized = CryptoAddress.normalize(chain, address)
            ?: throw AppError.Validation("That is not a valid ${chain.title} address. Copy it again from your wallet.")
        if (methods.any { it is PaymentMethod.CryptoWallet && it.address == normalized }) {
            throw AppError.Validation("That address is already saved.")
        }
        PaymentMethod.CryptoWallet(id(), chain, normalized)
    }

    override suspend fun removeMethod(id: String): Outcome<Unit> = lock.withLock {
        outcomeOf {
            if (!methods.removeAll { it.id == id }) throw AppError.Validation("That payment method is no longer saved.")
        }
    }

    private suspend fun <T : PaymentMethod> save(make: () -> T): Outcome<T> = lock.withLock {
        outcomeOf { make().also { methods += it } }
    }

    private fun balances(): List<Money> =
        transactions.filter { it.status == COMPLETED }
            .groupBy { it.amount.currency }
            .map { (currency, list) -> Money(list.sumOf { it.amount.minor }, currency) }
            .sortedBy { it.currency }

    private fun id(): String = "demo-${nextId++}"

    /** Fixed demo history: the amounts are the fixture, not rules. */
    @Suppress("MagicNumber")
    private fun seed(): List<WalletTransaction> {
        val now = clock.now()
        fun tx(kind: TransactionKind, minor: Long, ago: Duration, text: String, status: TransactionStatus = COMPLETED) =
            WalletTransaction(id(), kind, Money(minor, "USD"), now - ago, text, status)
        return listOf(
            tx(TransactionKind.TOP_UP, 5_000, 9.days, "Top-up from Visa •••• 4242"),
            tx(TransactionKind.ENTRY_FEE, -500, 6.days, "Riverside 5K entry"),
            tx(TransactionKind.PAYOUT, 1_200, 5.days, "Riverside 5K, 1st place"),
            tx(TransactionKind.ENTRY_FEE, -500, 2.days, "Hill sprint entry"),
            tx(TransactionKind.REFUND, 500, 1.days, "Hill sprint cancelled"),
            tx(TransactionKind.WITHDRAWAL, -2_000, 3.hours, "Withdrawal to Test Bank", TransactionStatus.PENDING),
        )
    }
}
