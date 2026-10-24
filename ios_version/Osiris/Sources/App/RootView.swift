import SwiftUI
import OsirisShared

/// Restores the session, then shows sign-in or the player's app.
struct RootView: View {
    let graph: AppGraph
    @StateObject private var session: Observed<SessionViewModel, any AuthState>

    init(graph: AppGraph) {
        self.graph = graph
        _session = StateObject(wrappedValue: Observed(graph.session()) { $0.state })
    }

    var body: some View {
        switch session.state {
        case is AuthStateSignedIn:
            SignedInRoot(graph: graph)
        case is AuthStateSignedOut:
            NavigationStack { LoginView(graph: graph) }
        default:
            ProgressView()
        }
    }
}

/// Today and every screen it opens, on one stack; signing out replaces the whole stack.
private struct SignedInRoot: View {
    let graph: AppGraph
    @StateObject private var nav = Navigator()

    var body: some View {
        NavigationStack(path: $nav.path) {
            TodayView(graph: graph)
                .navigationDestination(for: Route.self) { destination($0, graph: graph) }
        }
        .environmentObject(nav)
    }
}
