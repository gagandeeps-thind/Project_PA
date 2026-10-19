import SwiftUI
import OsirisShared

/// Restores the session, then shows sign-in or the player's app.
struct RootView: View {
    let graph: AppGraph
    @StateObject private var session: Observed<SessionViewModel, AuthState>

    init(graph: AppGraph) {
        self.graph = graph
        let vm = graph.session()
        _session = StateObject(wrappedValue: Observed(vm, state: vm.state))
    }

    var body: some View {
        switch session.state {
        case is AuthStateSignedIn:
            NavigationStack { TodayView(graph: graph) }
        case is AuthStateSignedOut:
            NavigationStack { LoginView(graph: graph) }
        default:
            ProgressView()
        }
    }
}
