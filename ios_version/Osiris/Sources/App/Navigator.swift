import SwiftUI
import OsirisShared

/// Screens pushed onto a tab's stack. Kotlin `Int` ids arrive in Swift as `Int32`.
enum Route: Hashable {
    case run(challengeId: Int32?)
    case challenges
    case challenge(Int32)
    case courses
    case clubs
    case club(String)
    case rankings
    case settings
    case exercises
    case exercise(String)
}

/// The signed-in navigation stack, shared so a screen can open another or close itself.
final class Navigator: ObservableObject {
    @Published var path: [Route] = []

    func open(_ route: Route) { path.append(route) }

    func back() {
        if !path.isEmpty { path.removeLast() }
    }
}

/// The view for each route.
@ViewBuilder
func destination(_ route: Route, graph: AppGraph) -> some View {
    switch route {
    case .run(let challengeId): RunView(graph: graph, challengeId: challengeId)
    case .challenges: ChallengeBoardView(graph: graph)
    case .challenge(let id): ChallengeDetailView(graph: graph, id: id)
    case .courses: CoursesView(graph: graph)
    case .clubs: CommunitiesView(graph: graph)
    case .club(let slug): CommunityDetailView(graph: graph, slug: slug)
    case .rankings: RankingsView(graph: graph)
    case .settings: SettingsView(graph: graph)
    case .exercises: ExerciseHubView(graph: graph)
    case .exercise(let key): ExerciseCameraView(graph: graph, key: key)
    }
}
