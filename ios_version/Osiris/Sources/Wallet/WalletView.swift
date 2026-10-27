import SwiftUI
import OsirisShared

/// Balances, saved methods and history. Demo builds label every figure as demo data.
struct WalletView: View {
    @StateObject private var model: Observed<WalletViewModel, WalletState>
    @State private var addingChain: Chain?
    @State private var address = ""

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.wallet()) { $0.state })
    }

    var body: some View {
        let s = model.state
        LoadableContent(state: s.overview, onRetry: { model.vm.refresh() }) { (overview: WalletOverview) in
            List {
                if s.isDemo {
                    Text("Demo wallet: sample figures only. No real money moves and nothing is charged.")
                        .foregroundStyle(OsirisColor.warning)
                        .listRowBackground(Color.clear)
                }
                Section {
                    VStack(alignment: .leading) {
                        SectionLabel(text: "Balance")
                        ForEach(overview.balances, id: \.currency) { Text($0.format()).font(.manrope(.largeTitle).bold()) }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .frostCard()
                }
                .listRowBackground(Color.clear)
                Section("Payment methods") {
                    ForEach(overview.methods, id: \.id) { m in
                        HStack {
                            Text(m.label)
                            Spacer()
                            Button(role: .destructive) { model.vm.remove(method: m) } label: { Image(systemName: "trash") }
                                .accessibilityLabel("Remove \(m.label)")
                                .disabled(s.busy)
                        }
                    }
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            Button("Add card") { model.vm.addCard() }
                            Button("Link bank") { model.vm.linkBank() }
                            ForEach(Chain.entries, id: \.title) { chain in
                                Button(chain.title) { address = ""; addingChain = chain }
                            }
                        }
                        .buttonStyle(.raised)
                        .disabled(s.busy)
                    }
                }
                .listRowBackground(Color.clear)
                Section("History") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            filter("All", selected: s.filter == nil) { model.vm.filter(kind: nil) }
                            ForEach(TransactionKind.entries, id: \.title) { k in
                                filter(k.title, selected: s.filter == k) { model.vm.filter(kind: k) }
                            }
                        }
                    }
                    ForEach(s.transactions, id: \.id) { t in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(t.description_)
                                Text("\(t.kind.title)  •  \(IosSupport.shared.localMinute(at: t.at))\(t.status == .pending ? "  •  pending" : "")")
                                    .font(.manrope(.footnote)).foregroundStyle(OsirisColor.muted)
                            }
                            Spacer()
                            Text(t.amount.format()).foregroundStyle(t.amount.minor < 0 ? OsirisColor.muted : OsirisColor.success)
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }
            .scrollContentBackground(.hidden)
            .refreshable { model.vm.refresh() }
        }
        .navigationTitle("Wallet")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
        .textInputAlert(
            "Add \(addingChain?.title ?? "") address",
            isPresented: Binding(get: { addingChain != nil }, set: { if !$0 { addingChain = nil } }),
            message: "Paste the address from your wallet app. Payouts sent to a wrong address cannot be recovered.",
            label: "Address",
            text: $address,
            confirm: "Save",
            dismiss: "Cancel",
            onConfirm: { value in
                if let chain = addingChain { model.vm.addCryptoWallet(chain: chain, address: value) }
                addingChain = nil
            },
            onDismiss: { addingChain = nil }
        )
    }

    private func filter(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action).buttonStyle(.raised).tint(selected ? OsirisColor.primary : OsirisColor.muted)
    }
}
