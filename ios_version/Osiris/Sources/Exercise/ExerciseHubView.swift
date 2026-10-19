import SwiftUI
import OsirisShared

/// Pick a bodyweight exercise, see personal bests and recent sets. Asks for camera consent
/// before the first set, from the shared ExerciseHubViewModel.
struct ExerciseHubView: View {
    @StateObject private var model: Observed<ExerciseHubViewModel, ExerciseHubState>
    @EnvironmentObject private var nav: Navigator
    @State private var bannerConsent = false

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.exerciseHub()) { $0.state })
    }

    private var vm: ExerciseHubViewModel { model.vm }

    var body: some View {
        let s = model.state
        LoadableContent(state: s.exercises, onRetry: { vm.refresh() }) { (tiles: [ExerciseTile]) in
            List {
                Section { privacy(consented: s.consented) }
                Section {
                    ForEach(tiles, id: \.spec.key) { t in
                        Button { vm.select(spec: t.spec) } label: { tile(t) }
                    }
                }
                if !s.recent.isEmpty {
                    Section(header: Text("Recent sets")) {
                        ForEach(s.recent, id: \.id) { recent($0) }
                    }
                }
            }
            .refreshable { vm.refresh() }
        }
        .background(OsirisColor.background)
        .navigationTitle("Bodyweight")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
        .onChange(of: s.open?.key) { key in
            guard let key else { return }
            vm.opened()
            nav.open(.exercise(key))
        }
        // Back from a set: show it in the recent list and sync it.
        .onReturn { vm.returned() }
        .exerciseConsentSheet(isPresented: Binding(
            get: { model.state.askConsentFor != nil },
            set: { _ in }
        )) { vm.consentAnswered(allow: $0) }
        .exerciseConsentSheet(isPresented: $bannerConsent) { allow in
            if allow { vm.grantConsent() }
        }
    }

    private func privacy(consented: Bool) -> some View {
        HStack(alignment: .top) {
            Image(systemName: "lock").foregroundStyle(OsirisColor.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text("Your camera stays on your phone")
                Text("Reps are counted on this device. No video or photos are saved or uploaded; only your rep count and timings are.")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            if !consented {
                Spacer()
                Button("ALLOW") { bannerConsent = true }.buttonStyle(.borderless)
            }
        }
    }

    private func tile(_ t: ExerciseTile) -> some View {
        HStack {
            Image(systemName: exerciseIcon(t.spec.key)).foregroundStyle(OsirisColor.secondary).frame(width: 28)
            VStack(alignment: .leading) {
                Text(t.spec.name).foregroundStyle(.white)
                Text(t.spec.camera == "front" ? "Face the camera" : "Side-on to the camera")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            if let best = t.best {
                Text("Best \(best)").foregroundStyle(OsirisColor.secondary)
            } else {
                Image(systemName: "chevron.right").foregroundStyle(OsirisColor.faint)
            }
        }
    }

    private func recent(_ r: RecentSetRow) -> some View {
        HStack {
            Image(systemName: exerciseIcon(r.exerciseKey)).font(.footnote).frame(width: 24)
            VStack(alignment: .leading) {
                Text(r.title)
                Text(r.time).font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            Text(r.status).foregroundStyle(Self.color(r.tone))
        }
    }

    private static func color(_ tone: RecentSetRowTone) -> Color {
        switch tone {
        case .good: return OsirisColor.success
        case .warn: return OsirisColor.warning
        case .bad: return OsirisColor.error
        default: return OsirisColor.faint
        }
    }
}
