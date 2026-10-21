package com.osiris.shared.presentation.wallet

import com.osiris.shared.core.error.Outcome
import com.osiris.shared.domain.repository.WalletRepository
import com.osiris.shared.domain.wallet.Chain
import com.osiris.shared.domain.wallet.PaymentMethod
import com.osiris.shared.domain.wallet.TransactionKind
import com.osiris.shared.domain.wallet.WalletOverview
import com.osiris.shared.domain.wallet.WalletTransaction
import com.osiris.shared.presentation.common.Loadable
import com.osiris.shared.presentation.common.SharedViewModel
import com.osiris.shared.presentation.common.UiMessage
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class WalletState(
    val overview: Loadable<WalletOverview> = Loadable.Loading,
    /** Null shows every kind. */
    val filter: TransactionKind? = null,
    val busy: Boolean = false,
    val isDemo: Boolean = true,
) {
    val transactions: List<WalletTransaction>
        get() = overview.valueOrNull?.transactions.orEmpty().filter { filter == null || it.kind == filter }
}

/** Balances, saved methods and a filterable history. */
class WalletViewModel(
    private val wallet: WalletRepository,
    dispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : SharedViewModel(dispatcher) {
    private val _state = MutableStateFlow(WalletState(isDemo = wallet.isDemo))
    val state: StateFlow<WalletState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        scope.launch { _state.update { it.copy(overview = Loadable.of(wallet.overview())) } }
    }

    fun filter(kind: TransactionKind?) = _state.update { it.copy(filter = kind) }

    fun addCard() = act("Card saved.") { wallet.addCard() }

    fun linkBank() = act("Bank account linked.") { wallet.linkBank() }

    /** An invalid address shows its reason as a message and saves nothing. */
    fun addCryptoWallet(chain: Chain, address: String) = act("${chain.title} address saved.") {
        wallet.addCryptoWallet(chain, address)
    }

    fun remove(method: PaymentMethod) = act("${method.label} removed.") { wallet.removeMethod(method.id) }

    private fun act(done: String, call: suspend () -> Outcome<*>) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true) }
        scope.launch {
            val ok = call().orShow() != null
            if (ok) {
                show(done, UiMessage.Kind.SUCCESS)
                _state.update { it.copy(overview = Loadable.of(wallet.overview())) }
            }
            _state.update { it.copy(busy = false) }
        }
    }
}
