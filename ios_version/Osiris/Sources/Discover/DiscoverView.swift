import SwiftUI
import OsirisShared

/// Happening now, upcoming, community and just-finished challenges. The button creates a
/// challenge from one of the player's courses; the map icon opens challenges near the player.
struct DiscoverView: View {
    @StateObject private var model: Observed<DiscoverViewModel, DiscoverState>
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.discover()) { $0.state })
    }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(HubSection.entries, id: \.wire) { section in
                        SectionLabel(text: section.title).padding(.horizontal, 16).padding(.top, 12)
                        row(section, model.state.sections[section])
                    }
                }
                .padding(.bottom, 96)
            }
            .refreshable { model.vm.refresh() }
            Button { nav.open(.courses) } label: {
                Label("CREATE CHALLENGE", systemImage: "plus").padding(.horizontal, 8)
            }
            .buttonStyle(.borderedProminent)
            .padding(16)
        }
        .navigationTitle("DISCOVER")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Button { nav.open(.challenges) } label: { Image(systemName: "map") }.accessibilityLabel("Challenges near me")
        }
        .messages(model)
    }

    @ViewBuilder private func row(_ section: HubSection, _ state: (any Loadable)?) -> some View {
        if let cards = state?.valueOrNull as? [DiscoverCard] {
            if cards.isEmpty {
                Text(section.empty).foregroundStyle(OsirisColor.faint).padding(.horizontal, 16)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(cards, id: \.challengeId) { card in
                            Button { nav.open(.challenge(card.challengeId)) } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(card.headline).font(.headline).lineLimit(1)
                                    Text(card.detail).foregroundStyle(OsirisColor.muted).lineLimit(3)
                                }
                                .frame(width: 260, height: 112, alignment: .topLeading)
                                .frostCard()
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 16)
                }
            }
        } else if let failed = state as? LoadableFailed {
            Button("\(failed.message) Tap to retry.") { model.vm.load(section: section) }
                .foregroundStyle(OsirisColor.error)
                .padding(.horizontal, 16)
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }
}
