import SwiftUI
import OsirisShared

/// Rank, XP to the next rank, totals and badges, from the shared ProgressViewModel.
struct ProgressScreen: View {
    @StateObject private var model: Observed<ProgressViewModel, any Loadable>

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.progress()) { $0.state })
    }

    var body: some View {
        LoadableContent(state: model.state, onRetry: { model.vm.refresh() }) { (p: ProgressSummary) in
            ScrollView { card(p).padding(16) }
                .refreshable { model.vm.refresh() }
        }
        .background(OsirisColor.background)
        .navigationTitle("PROGRESS")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
    }

    private func card(_ p: ProgressSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "medal.fill").foregroundStyle(OsirisColor.warning)
                Text(p.rank).font(.headline).kerning(1.5)
                Spacer()
                Text(p.toNext).foregroundStyle(OsirisColor.faint)
            }
            if p.progression.nextRankXp != nil {
                ProgressView(value: p.fraction).tint(OsirisColor.warning)
            }
            Text(p.totals).font(.footnote).foregroundStyle(OsirisColor.muted)
            if !p.progression.badges.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 6, alignment: .leading)], alignment: .leading, spacing: 6) {
                    ForEach(p.progression.badges, id: \.code) { b in
                        Label(b.label, systemImage: "checkmark.seal.fill")
                            .font(.caption)
                            .labelStyle(BadgeLabelStyle())
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
    }
}

/// A badge chip: the seal in the accent colour, then its name.
private struct BadgeLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 4) {
            configuration.icon.foregroundStyle(OsirisColor.secondary)
            configuration.title.lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.white.opacity(0.24)))
    }
}
