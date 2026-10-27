import SwiftUI
import OsirisShared

/// This week's local leaderboard, and city seasons with their club standings.
struct RankingsView: View {
    @StateObject private var model: Observed<RankingsViewModel, RankingsState>
    @EnvironmentObject private var nav: Navigator
    @State private var tab = 0

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.rankings()) { $0.state })
    }

    var body: some View {
        let s = model.state
        VStack(spacing: 0) {
            Picker("Rankings", selection: $tab) {
                Text("This week").tag(0)
                Text("Season").tag(1)
            }
            .pickerStyle(.segmented)
            .padding()
            List {
                if tab == 0 { local(s.local) } else { seasons(s.seasons) }
            }
            .refreshable { if tab == 0 { model.vm.refreshLocal() } else { model.vm.refreshSeasons() } }
        }
        .background(OsirisColor.background)
        .navigationTitle("Rankings")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
    }

    @ViewBuilder private func local(_ state: any Loadable) -> some View {
        if let board = state.valueOrNull as? Leaderboard {
            LeaderboardView(board: board)
        } else if let failed = state as? LoadableFailed {
            // Usually "set your city first": the way out is Settings.
            VStack(alignment: .leading, spacing: 12) {
                Text(failed.message)
                Button("Set my city") { nav.open(.settings) }.buttonStyle(.raised)
            }
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder private func seasons(_ state: any Loadable) -> some View {
        if let cards = state.valueOrNull as? [SeasonCard] {
            if cards.isEmpty {
                Text("No season in your city right now. Set your city in Settings to see local seasons.")
            }
            ForEach(cards, id: \.season.slug) { card in
                Section { seasonCard(card) }
            }
        } else if let failed = state as? LoadableFailed {
            Text(failed.message).foregroundStyle(OsirisColor.error)
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }

    private func seasonCard(_ card: SeasonCard) -> some View {
        let season = card.season
        return VStack(alignment: .leading, spacing: 8) {
            Text(season.name).font(.manrope(.title3).bold())
            Text(card.status).foregroundStyle(OsirisColor.muted)
            if let description = season.description_ { Text(description) }
            if season.entered {
                Text("You're in. Every active day counts.").foregroundStyle(OsirisColor.success)
            } else {
                Button("Join the season") { model.vm.joinSeason(slug: season.slug) }
                    .buttonStyle(.key)
            }
            if let board = card.board {
                if !board.communities.isEmpty {
                    SectionLabel(text: "Club standings").padding(.top, 8)
                    ForEach(board.communities, id: \.rank) { c in
                        HStack {
                            Text("#\(c.rank)")
                            Text(c.name).fontWeight(c.isMine ? .bold : .regular)
                            Spacer()
                            Text("\(c.averagePoints) avg pts")
                        }
                    }
                }
                LeaderboardView(board: board.players, compact: true).padding(.top, 8)
            }
        }
        .padding(.vertical, 6)
        .buttonStyle(.borderless)
    }
}
