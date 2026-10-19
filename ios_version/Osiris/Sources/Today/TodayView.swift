import SwiftUI
import OsirisShared

/// Home screen: today's quest and the week, from the shared TodayViewModel.
struct TodayView: View {
    @StateObject private var model: Observed<TodayViewModel, Loadable>

    init(graph: AppGraph) {
        let vm = graph.today()
        _model = StateObject(wrappedValue: Observed(vm, state: vm.state))
    }

    var body: some View {
        content
            .navigationTitle("OSIRIS")
            .refreshable { model.vm.refresh() }
            .modifier(MessageBanner(text: model.message?.text, onShown: model.messageShown))
    }

    @ViewBuilder private var content: some View {
        switch model.state {
        case let ready as LoadableReady<TodayData>:
            if let t = ready.value { today(t) }
        case let failed as LoadableFailed:
            VStack(spacing: 12) {
                Text(failed.message).foregroundStyle(OsirisColor.error)
                if failed.canRetry { Button("TRY AGAIN") { model.vm.refresh() } }
            }
        default:
            ProgressView()
        }
    }

    private func today(_ t: TodayData) -> some View {
        List {
            Section {
                Text("Hi \(t.displayName)").font(.title2.bold())
                Text("\(t.performanceRank) \(t.identity)  •  \(t.xp) XP").foregroundStyle(.secondary)
            }
            Section(t.today.heading) {
                Text(t.today.title).font(.headline)
                Text(t.today.description_).foregroundStyle(.secondary)
                ProgressView(value: t.today.fraction)
            }
            Section("THIS WEEK") {
                Text("\(t.week.activeDays) of \(t.week.activeDaysTarget) active days. Rest days never break your streak.")
            }
            Section("Tomorrow") { Text(t.tomorrow.title) }
        }
    }
}
