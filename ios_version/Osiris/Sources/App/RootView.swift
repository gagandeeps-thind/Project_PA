import SwiftUI
import OsirisShared

/// The app root, guarded by the shared navigator: permission primer on first launch, then
/// sign-in, then the tabbed app. A restored session opens straight to Home.
struct RootView: View {
    let graph: AppGraph
    @StateObject private var navigator: Observed<AppNavigatorViewModel, any RootState>

    init(graph: AppGraph) {
        self.graph = graph
        _navigator = StateObject(wrappedValue: Observed(graph.navigator()) { $0.state })
    }

    var body: some View {
        ZStack {
            FrostBackground()
            switch navigator.state {
            case let signedIn as RootStateSignedIn:
                SignedInRoot(graph: graph, pending: signedIn.pending, onPendingOpened: { navigator.vm.pendingOpened() })
            case let signedOut as RootStateSignedOut:
                NavigationStack {
                    if signedOut.invite != nil || signedOut.referral != nil {
                        OnboardingView(graph: graph, inviteToken: signedOut.invite, referralCode: signedOut.referral)
                    } else {
                        LoginView(graph: graph)
                    }
                }
            case is RootStatePermissionPrimer:
                PermissionPrimerView(graph: graph)
            default:
                ProgressView()
            }
        }
        .onOpenURL { url in _ = navigator.vm.open(link: url.absoluteString) }
    }
}

/// The bar's sections. Wallet joins when its screen ships.
private enum AppSection: Hashable {
    case home, discover, social, profile
}

/// Four tabs, each with its own stack; signing out replaces the whole tree.
private struct SignedInRoot: View {
    let graph: AppGraph
    let pending: (any Destination)?
    let onPendingOpened: () -> Void
    @State private var section: AppSection = .home
    @StateObject private var home = Navigator()
    @StateObject private var discover = Navigator()
    @StateObject private var social = Navigator()
    @StateObject private var profile = Navigator()

    var body: some View {
        TabView(selection: $section) {
            stack(home) { TodayView(graph: graph) }
                .tabItem { Label("Home", systemImage: "house") }
                .tag(AppSection.home)
            stack(discover) { ChallengeBoardView(graph: graph) }
                .tabItem { Label("Discover", systemImage: "safari") }
                .tag(AppSection.discover)
            stack(social) { RankingsView(graph: graph) }
                .tabItem { Label("Social", systemImage: "person.3") }
                .tag(AppSection.social)
            stack(profile) { ProgressScreen(graph: graph) }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
                .tag(AppSection.profile)
        }
        .onAppear { open(pending) }
        // Kotlin objects are NSObjects, which gives the pending link value equality.
        .onChange(of: pending as? NSObject) { _ in open(pending) }
    }

    private func stack<Root: View>(_ nav: Navigator, @ViewBuilder root: () -> Root) -> some View {
        NavigationStack(path: Binding(get: { nav.path }, set: { nav.path = $0 })) {
            root().navigationDestination(for: Route.self) { destination($0, graph: graph) }
        }
        .environmentObject(nav)
    }

    private func open(_ destination: (any Destination)?) {
        guard let destination else { return }
        switch destination {
        case let tab as DestinationSection:
            switch tab.tab {
            case .discover: section = .discover
            case .social: section = .social
            case .profile: section = .profile
            default: section = .home
            }
        case let challenge as DestinationChallenge:
            section = .discover
            discover.open(.challenge(challenge.id))
        case let club as DestinationCommunity:
            section = .home
            home.open(.club(club.slug))
        default:
            // Invites and referrals: the player already has an account; the challenge is on Discover.
            section = .discover
        }
        onPendingOpened()
    }
}
