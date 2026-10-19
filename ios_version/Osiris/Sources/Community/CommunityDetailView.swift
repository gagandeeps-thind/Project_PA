import SwiftUI
import OsirisShared

/// One club: perk, join code, join or leave, team goal, featured challenges and the weekly board.
struct CommunityDetailView: View {
    @StateObject private var model: Observed<CommunityDetailViewModel, CommunityDetailState>
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph, slug: String) {
        _model = StateObject(wrappedValue: Observed(graph.community(slug: slug)) { $0.state })
    }

    var body: some View {
        let s = model.state
        let name = (s.detail.valueOrNull as? CommunityDetail)?.community.name
        LoadableContent(state: s.detail, onRetry: { model.vm.refresh() }) { (detail: CommunityDetail) in
            content(detail)
        }
        .background(OsirisColor.background)
        .navigationTitle(name ?? "GROUP")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    Button("Report this group") { model.vm.report() }
                } label: { Image(systemName: "ellipsis.circle") }
                .accessibilityLabel("More")
            }
        }
        .messages(model)
        .onChange(of: s.left) { if $0 { nav.back() } }
    }

    private func content(_ detail: CommunityDetail) -> some View {
        let c = detail.community
        return List {
            Section {
                // The club's brand colour, as the Flutter app tints its header.
                RoundedRectangle(cornerRadius: 3).fill(OsirisColor.brand(c.brandColor)).frame(height: 6)
                HStack {
                    Text(c.kindLabel).foregroundStyle(OsirisColor.muted)
                    if c.verified {
                        Label("Verified", systemImage: "checkmark.seal.fill").foregroundStyle(OsirisColor.secondary)
                    }
                }
                if let description = c.description_ { Text(description) }
            }
            if let perk = c.perkText {
                Section {
                    Label {
                        VStack(alignment: .leading) {
                            Text("Member perk")
                            Text(perk).font(.subheadline).foregroundStyle(OsirisColor.muted)
                        }
                    } icon: { Image(systemName: "gift.fill").foregroundStyle(OsirisColor.warning) }
                }
            }
            if let code = c.joinCode {
                Section {
                    Label {
                        VStack(alignment: .leading) {
                            Text("Join code: \(code)")
                            Text("Group ID: \(c.slug). Share both with your members.").font(.subheadline).foregroundStyle(OsirisColor.muted)
                        }
                    } icon: { Image(systemName: "key") }
                }
            }
            if c.myRole != "owner" {
                Section {
                    Button(c.isMember ? "LEAVE GROUP" : "JOIN GROUP") {
                        if c.isMember { model.vm.leave() } else { model.vm.join(joinCode: nil) }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            if let goal = c.teamGoal { Section { teamGoal(goal) } }
            Section("GROUP CHALLENGES") {
                if detail.challenges.isEmpty { Text("No featured challenges right now.") }
                ForEach(detail.challenges, id: \.id) { ch in
                    Button { nav.open(.challenge(ch.id)) } label: {
                        HStack {
                            Image(systemName: "flag")
                            VStack(alignment: .leading) {
                                Text(ch.title)
                                Text("\(Format.shared.distance(metres: ch.courseDistanceM))  •  target \(Format.shared.duration(seconds: ch.targetSeconds))  •  free")
                                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").foregroundStyle(OsirisColor.faint)
                        }
                    }
                }
            }
            Section {
                if let board = detail.leaderboard {
                    LeaderboardView(board: board)
                } else if !c.isMember {
                    Text("Join to see the weekly leaderboard.").foregroundStyle(OsirisColor.muted)
                }
            }
        }
        .refreshable { model.vm.refresh() }
    }

    private func teamGoal(_ goal: TeamGoal) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel(text: "Team goal this week")
            Text("\(Format.shared.fixed(value: goal.progressKm, decimals: 1)) of \(Format.shared.fixed(value: goal.goalKm, decimals: 0)) km together")
                .font(.headline)
            ProgressView(value: goal.fraction)
            Text(goal.completed
                 ? "Goal reached. Nice work, team."
                 : "\(goal.activeMembers) members active so far. Every verified km counts (up to 10 km a day each).")
                .font(.footnote).foregroundStyle(OsirisColor.muted)
        }
        .padding(.vertical, 6)
    }
}
