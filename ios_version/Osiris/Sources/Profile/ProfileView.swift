import SwiftUI
import OsirisShared

/// Header with rank, XP gauge through the current rank, metrics grid and badges.
struct ProfileView: View {
    @StateObject private var model: Observed<ProfileViewModel, any Loadable>
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.profile()) { $0.state })
    }

    var body: some View {
        LoadableContent(state: model.state, onRetry: { model.vm.refresh() }) { (p: ProfileSummary) in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header(p)
                    gauge(p)
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible())], spacing: 12) {
                        ForEach(p.metrics, id: \.label) { m in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(m.value).font(.title3.bold())
                                Text(m.label.uppercased()).font(.caption).kerning(1).foregroundStyle(OsirisColor.muted)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .frostCard()
                        }
                    }
                    badges(p)
                }
                .padding(16)
            }
            .refreshable { model.vm.refresh() }
        }
        .navigationTitle("PROFILE")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Button { nav.open(.support) } label: { Image(systemName: "bubble.left.and.bubble.right") }
                .accessibilityLabel("Live support")
            Button { nav.open(.settings) } label: { Image(systemName: "gearshape") }.accessibilityLabel("Settings")
        }
        .messages(model)
    }

    private func header(_ p: ProfileSummary) -> some View {
        HStack(spacing: 16) {
            Text(String(p.name.prefix(1)).uppercased())
                .font(.title.bold())
                .frame(width: 64, height: 64)
                .background(OsirisColor.primary.opacity(0.24), in: Circle())
            VStack(alignment: .leading) {
                Text(p.name).font(.title2)
                Text("\(p.rank)  •  \(p.goal)").kerning(1).foregroundStyle(OsirisColor.muted)
            }
        }
    }

    private func gauge(_ p: ProfileSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(p.xp).bold()
                Spacer()
                Text(p.toNext).foregroundStyle(OsirisColor.faint)
            }
            ProgressView(value: p.gauge).tint(OsirisColor.warning)
        }
        .frostCard()
    }

    @ViewBuilder private func badges(_ p: ProfileSummary) -> some View {
        if !p.progression.badges.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 6, alignment: .leading)], alignment: .leading, spacing: 6) {
                ForEach(p.progression.badges, id: \.code) { b in
                    Label(b.label, systemImage: "checkmark.seal.fill").font(.caption)
                }
            }
        }
    }
}
