import StoreKit
import SwiftUI
import OsirisShared

/// The Mana Crystal Store: App Store products with their local prices, buy and restore.
struct CrystalStoreView: View {
    let graph: AppGraph
    @EnvironmentObject private var store: CrystalStore

    var body: some View {
        Group {
            if store.products.isEmpty {
                if store.loading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    EmptyState(
                        icon: "sparkles",
                        title: "The store is not available right now.",
                        detail: store.loadFailed ? "Check your connection and try again." : nil,
                        actionLabel: "Try again",
                        action: { Task { await store.loadProducts() } }
                    )
                }
            } else {
                List {
                    Section {
                        ForEach(store.products, id: \.id) { product in
                            row(product).frostCard()
                        }
                    }
                    .listRowBackground(Color.clear)
                    Section {
                        Button("Restore purchases") { Task { await store.restore() } }
                            .buttonStyle(.raised)
                            .disabled(store.busy)
                        if store.products.contains(where: { $0.type == .autoRenewable }) {
                            Text(
                                "Osiris Pass renews automatically until you cancel it in Settings > Apple ID > Subscriptions, "
                                    + "at least 24 hours before the period ends."
                            )
                                .font(.manrope(.footnote)).foregroundStyle(OsirisColor.muted)
                        }
                        HStack {
                            legalLink("Terms of Use", path: "/terms")
                            Spacer()
                            legalLink("Privacy Policy", path: "/privacy")
                        }
                        .font(.manrope(.footnote))
                    }
                    .listRowBackground(Color.clear)
                }
                .scrollContentBackground(.hidden)
                .refreshable { await store.loadProducts() }
            }
        }
        .navigationTitle("Mana Crystal Store")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await store.loadProducts()
            await store.retryUnfinished()
        }
        .modifier(MessageBanner(text: store.notice, onShown: { store.notice = nil }))
    }

    private func row(_ product: Product) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(product.displayName).font(.manrope(.headline))
                Text(product.description).font(.manrope(.footnote)).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            Button(product.displayPrice) { Task { await store.buy(product) } }
                .buttonStyle(.key)
                .disabled(store.busy)
                .accessibilityLabel("Buy \(product.displayName) for \(product.displayPrice)")
        }
    }

    @ViewBuilder private func legalLink(_ title: String, path: String) -> some View {
        if let url = URL(string: graph.config.apiBaseUrl + path) {
            Link(title, destination: url)
        }
    }
}
