import AVFoundation
import CoreLocation
import CoreMotion
import SwiftUI
import UserNotifications
import OsirisShared

/// Asks iOS for one primer permission and reports the answer. HealthKit is asked for through its
/// own flow once the health integration ships, so it is not offered here yet.
@MainActor
final class PermissionAsker: NSObject, ObservableObject, CLLocationManagerDelegate {
    static let offered: Set<DevicePermission> = [.location, .activity, .camera, .notifications]

    private let location = CLLocationManager()
    private let motion = CMMotionActivityManager()
    private var locationAnswer: ((PermissionStatus) -> Void)?

    override init() {
        super.init()
        location.delegate = self
    }

    func statuses() async -> [DevicePermission: PermissionStatus] {
        var out: [DevicePermission: PermissionStatus] = [:]
        if [.authorizedWhenInUse, .authorizedAlways].contains(location.authorizationStatus) { out[.location] = .granted }
        if CMMotionActivityManager.authorizationStatus() == .authorized { out[.activity] = .granted }
        if AVCaptureDevice.authorizationStatus(for: .video) == .authorized { out[.camera] = .granted }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        if settings.authorizationStatus == .authorized { out[.notifications] = .granted }
        return out
    }

    func ask(_ permission: DevicePermission) async -> PermissionStatus {
        switch permission {
        case .location:
            return await withCheckedContinuation { done in
                locationAnswer = { done.resume(returning: $0) }
                location.requestWhenInUseAuthorization()
            }
        case .activity:
            // Motion has no request API: the first query shows the prompt.
            return await withCheckedContinuation { done in
                let now = Date()
                motion.queryActivityStarting(from: now, to: now, to: .main) { _, _ in
                    done.resume(returning: CMMotionActivityManager.authorizationStatus() == .authorized ? .granted : .denied)
                }
            }
        case .camera:
            return await AVCaptureDevice.requestAccess(for: .video) ? .granted : .denied
        case .notifications:
            let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
            return granted ? .granted : .denied
        default:
            return .denied
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            guard status != .notDetermined, let answer = locationAnswer else { return }
            locationAnswer = nil
            answer([.authorizedWhenInUse, .authorizedAlways].contains(status) ? .granted : .denied)
        }
    }
}

/// Explains each permission before sign-in; every one is optional (App Store 5.1.1).
struct PermissionPrimerView: View {
    @StateObject private var model: Observed<PermissionPrimerViewModel, PermissionPrimerState>
    @StateObject private var asker = PermissionAsker()
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var phase

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.permissionPrimer(available: PermissionAsker.offered)) { $0.state })
    }

    private var vm: PermissionPrimerViewModel { model.vm }

    var body: some View {
        let palette = FrostPalette(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: CGFloat(FrostMatte.Spacing.shared.M)) {
                Text("Before you start").font(.title2.bold()).foregroundStyle(palette.textPrimary)
                Text("Osiris works without any of these. Allow what you want now; we ask again when you use the feature.")
                    .font(.callout).foregroundStyle(palette.textSecondary)
                ForEach(model.state.items, id: \.permission) { item in
                    row(item, palette: palette)
                }
                Toggle(isOn: Binding(get: { model.state.telemetry }, set: { vm.setTelemetry(granted: $0) })) {
                    VStack(alignment: .leading) {
                        Text("Share crash reports").font(.headline)
                        Text("Anonymous diagnostics that help us fix crashes. Off unless you turn it on.")
                            .font(.caption).foregroundStyle(palette.textSecondary)
                    }
                }
                .frostCard()
                Button("Continue") { vm.finish() }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
            }
            .padding(CGFloat(FrostMatte.Spacing.shared.XL))
        }
        .task { await refresh() }
        .onChange(of: phase) { if $0 == .active { Task { await refresh() } } }
        .onChange(of: model.state.requesting) { asked in
            guard let asked else { return }
            Task { vm.onResult(permission: asked, status: await asker.ask(asked)) }
        }
    }

    private func refresh() async {
        vm.onStatuses(statuses: await asker.statuses())
    }

    @ViewBuilder
    private func row(_ item: PermissionItem, palette: FrostPalette) -> some View {
        HStack(spacing: CGFloat(FrostMatte.Spacing.shared.M)) {
            Image(systemName: symbol(item.permission)).foregroundStyle(palette.accent)
            VStack(alignment: .leading) {
                Text(item.title).font(.headline)
                Text(item.purpose).font(.caption).foregroundStyle(palette.textSecondary)
            }
            Spacer()
            switch item.status {
            case .granted: Text("Allowed").font(.callout.bold()).foregroundStyle(palette.success)
            case .denied: Text("Skipped").font(.callout.bold()).foregroundStyle(palette.textMuted)
            default: Button("Allow") { vm.request(permission: item.permission) }.buttonStyle(.bordered)
            }
        }
        .frostCard()
    }

    private func symbol(_ permission: DevicePermission) -> String {
        switch permission {
        case .location: return "location"
        case .activity: return "figure.walk"
        case .health: return "heart"
        case .camera: return "camera"
        default: return "bell"
        }
    }
}
