import SwiftUI
import OsirisShared

/// Open challenges near the player, within a chosen radius.
struct ChallengeBoardView: View {
    @StateObject private var model: Observed<ChallengeBoardViewModel, ChallengeBoardState>
    @StateObject private var location = LocationTracker()
    @EnvironmentObject private var nav: Navigator
    @State private var unavailable: String?

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.challengeBoard()) { $0.state })
    }

    var body: some View {
        let s = model.state
        Group {
            if let unavailable {
                Text(unavailable).foregroundStyle(OsirisColor.error).multilineTextAlignment(.center).padding(24)
            } else {
                LoadableContent(state: s.challenges, onRetry: { model.vm.refresh() }) { (list: [ChallengeSummary]) in
                    List {
                        if list.isEmpty {
                            EmptyState(
                                icon: "trophy",
                                title: "No open challenges within \(Int(s.radiusKm)) km.",
                                detail: "Record a run, register it as a course, and publish the first one."
                            )
                            .listRowBackground(Color.clear)
                        }
                        ForEach(list, id: \.id) { c in
                            Button { nav.open(.challenge(c.id)) } label: { ChallengeTile(c: c) }
                        }
                    }
                    .refreshable { model.vm.refresh() }
                }
            }
        }
        .background(OsirisColor.background)
        .navigationTitle("CHALLENGES")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    ForEach(s.radii.map(\.doubleValue), id: \.self) { r in
                        Button("Within \(Int(r)) km") { model.vm.setRadius(km: r) }
                    }
                } label: { Image(systemName: "scope") }
                .accessibilityLabel("Search radius")
            }
        }
        .messages(model)
        .task {
            if let p = await location.currentPosition(askIfNeeded: true) {
                model.vm.onPosition(position: p)
            } else {
                unavailable = IosSupport.shared.locationOff().userMessage
            }
        }
        // Back from a challenge: a join or attempt changes its chip.
        .onReturn { model.vm.refresh() }
    }
}

/// One challenge in a list: distance, time to beat, how far away, when it closes, the reward.
struct ChallengeTile: View {
    let c: ChallengeSummary

    var body: some View {
        let away = c.distanceKm.map { "~\(Format.shared.fixed(value: $0.doubleValue, decimals: 1)) km away • " } ?? ""
        HStack(spacing: 12) {
            Image(systemName: "trophy.fill").font(.title).foregroundStyle(OsirisColor.warning)
            VStack(alignment: .leading, spacing: 2) {
                Text(c.title).fontWeight(.bold)
                Text("\(Format.shared.distance(metres: c.courseDistanceM)) • beat \(Format.shared.duration(seconds: c.targetSeconds))")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
                Text("\(away)\(IosSupport.shared.closesIn(c: c)) • \(c.attemptCount) attempts")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text("+\(c.winXp) XP").fontWeight(.bold).foregroundStyle(OsirisColor.primary)
                if c.isMine {
                    Chip(label: "Yours", color: OsirisColor.secondary)
                } else if let attempt = c.myAttempt {
                    Chip(label: attempt.label, color: OsirisColor.success)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}
