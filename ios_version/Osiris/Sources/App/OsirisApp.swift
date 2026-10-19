import SwiftUI
import OsirisShared

/// Builds the shared graph once per launch; every screen asks it for a view model.
@main
struct OsirisApp: App {
    private let graph = AppGraph(
        config: AppConfig.companion.fromBuild(platform: Platform.ios),
        platform: IosPlatform.shared.create(recordingAllowed: false)
    )

    var body: some Scene {
        WindowGroup {
            RootView(graph: graph)
                .preferredColorScheme(.dark)
                .tint(OsirisColor.primary)
        }
    }
}
