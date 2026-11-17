import StoreKit
import SwiftUI
import OsirisShared

/// StoreKit 2 purchases for the Mana Crystal Store. The server grants everything: each transaction's
/// signed form goes to `POST /api/v2/payments/app-store/verify` (`graph.store().verifyAppStore`), and
/// the transaction is finished only once the server has recorded it, so StoreKit redelivers it until
/// then. See docs/architecture/app-store-billing-ios.md.
@MainActor
final class CrystalStore: ObservableObject {
    /// Same product ids as Android (`PlayBillingCatalog`); the server maps them the same way.
    static let crystalPacks = ["osiris_crystals_starter", "osiris_crystals_adventurer", "osiris_crystals_champion"]
    /// Founder Pack and Osiris Pass: offered only when `features.passProducts` is on, as on Android.
    static let passProducts = ["osiris_founder_pack", "osiris_pass_monthly", "osiris_pass_annual"]

    @Published private(set) var products: [Product] = []
    @Published private(set) var loading = false
    @Published private(set) var loadFailed = false
    @Published private(set) var busy = false
    @Published var notice: String?

    private let support: StoreSupport
    private var updates: Task<Void, Never>?

    // nonisolated: RootView builds it in its (non-main-actor) init through StateObject.
    nonisolated init(graph: AppGraph) {
        support = graph.store()
    }

    var sellsPass: Bool { support.sellsPass }

    /// Call once at launch: listens for transactions made outside the app or approved later (Ask to
    /// Buy, renewals, interrupted purchases) and retries the ones the server has not confirmed yet.
    func start() {
        guard updates == nil else { return }
        updates = Task { [weak self] in
            for await result in Transaction.updates {
                await self?.deliver(result, announce: true)
            }
        }
        Task { await retryUnfinished() }
    }

    func loadProducts() async {
        let ids = Self.crystalPacks + (sellsPass ? Self.passProducts : [])
        loading = true
        defer { loading = false }
        do {
            let loaded = try await Product.products(for: ids)
            products = ids.compactMap { id in loaded.first { $0.id == id } }
            loadFailed = products.isEmpty
        } catch {
            loadFailed = true
        }
    }

    func buy(_ product: Product) async {
        guard let token = accountToken else {
            notice = "Sign in to buy Mana Crystals."
            return
        }
        busy = true
        defer { busy = false }
        do {
            switch try await product.purchase(options: [.appAccountToken(token)]) {
            case .success(let result):
                await deliver(result, announce: true)
            case .pending:
                notice = "Waiting for approval. Your crystals arrive once the purchase is approved."
            case .userCancelled:
                break
            @unknown default:
                break
            }
        } catch {
            notice = "The App Store could not complete the purchase."
        }
    }

    /// App Review requires this: asks the App Store for this Apple ID's purchases and sends the ones
    /// that still grant something (Founder Pack, an active pass) to the server again.
    func restore() async {
        busy = true
        defer { busy = false }
        do {
            try await AppStore.sync()
        } catch {
            notice = "Could not reach the App Store. Try again."
            return
        }
        for await result in Transaction.currentEntitlements {
            await deliver(result, announce: false)
        }
        await retryUnfinished()
        notice = "Purchases restored."
    }

    /// Sends every transaction the server has not confirmed yet (e.g. the app closed mid-purchase).
    func retryUnfinished() async {
        for await result in Transaction.unfinished {
            await deliver(result, announce: false)
        }
    }

    private var accountToken: UUID? {
        support.appStoreAccountToken().flatMap { UUID(uuidString: $0) }
    }

    /// The server checks Apple's signature itself, so even a result StoreKit could not verify is sent.
    private func deliver(_ result: VerificationResult<Transaction>, announce: Bool) async {
        // Signed out: the server cannot take it yet. It stays unfinished and is retried after sign-in.
        guard accountToken != nil else { return }
        let transaction: Transaction
        switch result {
        case .verified(let t), .unverified(let t, _):
            transaction = t
        }
        let answer: StoreVerifyResult
        do {
            answer = try await support.verifyAppStore(signedTransaction: result.jwsRepresentation)
        } catch {
            return
        }
        guard answer.finish, let verification = answer.verification else {
            if announce { notice = answer.error ?? "Your purchase could not be confirmed yet. It will be retried." }
            return
        }
        await transaction.finish()
        guard announce else { return }
        if verification.crystalsCredited > 0 {
            let balance = verification.balance.map { " Balance: \($0.intValue)." } ?? ""
            notice = "+\(verification.crystalsCredited) Mana Crystals.\(balance)"
        } else if verification.entitled {
            notice = "Purchase confirmed."
        }
    }
}
