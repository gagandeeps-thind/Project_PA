import SwiftUI
import UIKit
import OsirisShared

/// Builds the shared graph once per launch; every screen asks it for a view model.
@main
struct OsirisApp: App {
    private let graph = AppGraph(
        config: AppConfig.companion.fromBuild(platform: Platform.ios),
        platform: IosPlatform.shared.create(recordingAllowed: false)
    )

    init() {
        // Navigation titles are UIKit, so they take Manrope through the appearance proxy.
        let bar = UINavigationBar.appearance()
        bar.titleTextAttributes = [.font: FrostFont.uiFont(size: 17, weight: 700)]
        bar.largeTitleTextAttributes = [.font: FrostFont.uiFont(size: 34, weight: 800)]
    }

    var body: some Scene {
        WindowGroup {
            RootView(graph: graph)
                .font(.manrope(.body))
                .preferredColorScheme(.dark)
                .tint(OsirisColor.primary)
        }
    }
}
