package com.osiris.player.ui.wallet

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.osiris.player.ui.common.LoadableContent
import com.osiris.player.ui.common.OsirisScaffold
import com.osiris.player.ui.common.SectionHeader
import com.osiris.player.ui.common.TextInputDialog
import com.osiris.player.ui.common.localMinute
import com.osiris.player.ui.common.rememberShared
import com.osiris.player.ui.design.FrostCard
import com.osiris.player.ui.theme.OsirisColors
import com.osiris.shared.domain.wallet.Chain
import com.osiris.shared.domain.wallet.TransactionKind
import com.osiris.shared.domain.wallet.TransactionStatus
import com.osiris.shared.presentation.AppGraph

/** Balances, saved methods and history. Demo builds label every figure as demo data. */
@Composable
fun WalletScreen(graph: AppGraph) {
    val vm = rememberShared { graph.wallet() }
    val s by vm.state.collectAsStateWithLifecycle()
    var addingChain by rememberSaveable { mutableStateOf<Chain?>(null) }

    OsirisScaffold("WALLET", vm) { padding ->
        PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize().padding(padding)) {
            LoadableContent(s.overview, onRetry = vm::refresh) { overview ->
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
                    if (s.isDemo) {
                        item {
                            Text(
                                "Demo wallet: sample figures only. No real money moves and nothing is charged.",
                                color = OsirisColors.Warning,
                                modifier = Modifier.padding(horizontal = 16.dp),
                            )
                        }
                    }
                    item {
                        FrostCard(Modifier.fillMaxWidth().padding(16.dp)) {
                            Text("BALANCE", color = OsirisColors.Muted)
                            for (b in overview.balances) Text(b.format(), style = MaterialTheme.typography.headlineMedium)
                        }
                    }
                    item { SectionHeader("Payment methods") }
                    items(overview.methods, key = { it.id }) { m ->
                        ListItem(
                            headlineContent = { Text(m.label) },
                            trailingContent = {
                                IconButton(onClick = { vm.remove(m) }, enabled = !s.busy) {
                                    Icon(Icons.Outlined.Delete, "Remove ${m.label}")
                                }
                            },
                            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                        )
                    }
                    item {
                        Row(
                            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedButton(onClick = vm::addCard, enabled = !s.busy) { Text("ADD CARD") }
                            OutlinedButton(onClick = vm::linkBank, enabled = !s.busy) { Text("LINK BANK") }
                            for (chain in Chain.entries) {
                                OutlinedButton(onClick = { addingChain = chain }, enabled = !s.busy) { Text(chain.title.uppercase()) }
                            }
                        }
                    }
                    item { SectionHeader("History") }
                    item {
                        Row(
                            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            FilterChip(selected = s.filter == null, onClick = { vm.filter(null) }, label = { Text("All") })
                            for (k in TransactionKind.entries) {
                                FilterChip(selected = s.filter == k, onClick = { vm.filter(k) }, label = { Text(k.title) })
                            }
                        }
                    }
                    items(s.transactions, key = { it.id }) { t ->
                        val pending = if (t.status == TransactionStatus.PENDING) "  •  pending" else ""
                        ListItem(
                            headlineContent = { Text(t.description) },
                            supportingContent = { Text("${t.kind.title}  •  ${t.at.localMinute()}$pending") },
                            trailingContent = {
                                Text(t.amount.format(), color = if (t.amount.minor < 0) OsirisColors.Muted else OsirisColors.Success)
                            },
                            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                        )
                    }
                }
            }
        }
    }

    addingChain?.let { chain ->
        TextInputDialog(
            title = "Add ${chain.title} address",
            body = "Paste the address from your wallet app. Payouts sent to a wrong address cannot be recovered.",
            label = "Address",
            confirm = "SAVE",
            onConfirm = {
                vm.addCryptoWallet(chain, it)
                addingChain = null
            },
            dismiss = "CANCEL",
            onDismiss = { addingChain = null },
            maxLength = 64,
        )
    }
}
