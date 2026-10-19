import SwiftUI
import OsirisShared

/// One challenge: terms, safety notes, the player's attempt, and join or run.
struct ChallengeDetailView: View {
    @StateObject private var model: Observed<ChallengeDetailViewModel, ChallengeDetailState>
    @EnvironmentObject private var nav: Navigator
    @State private var confirmBlock = false
    @State private var shareText: SharedText?

    init(graph: AppGraph, id: Int32) {
        _model = StateObject(wrappedValue: Observed(graph.challengeDetail(id: id)) { $0.state })
    }

    var body: some View {
        let s = model.state
        LoadableContent(state: s.detail, onRetry: { model.vm.refresh() }) { (detail: ChallengeDetail) in
            content(detail, joining: s.joining)
        }
        .background(OsirisColor.background)
        .navigationTitle("CHALLENGE")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .navigationBarTrailing) {
                if s.canInvite {
                    Button { model.vm.invite() } label: { Image(systemName: "person.badge.plus") }
                        .accessibilityLabel("Invite a friend")
                }
                if s.canReport {
                    Menu {
                        ForEach(s.reportReasons, id: \.wire) { reason in
                            Button(reason.label) { model.vm.report(reason: reason) }
                        }
                        Button("Block this player", role: .destructive) { confirmBlock = true }
                    } label: { Image(systemName: "ellipsis.circle") }
                    .accessibilityLabel("Report or block")
                }
            }
        }
        .alert("Block this player?", isPresented: $confirmBlock) {
            Button("BLOCK", role: .destructive) { model.vm.blockCreator() }
            Button("CANCEL", role: .cancel) {}
        } message: {
            Text("You won't see this player's challenges. You can unblock them in Settings.")
        }
        .shareSheet(s.share) { model.vm.shared(completed: $0) }
        .sheet(item: $shareText) { ShareSheet(text: $0.text) }
        .messages(model)
        .onChange(of: s.closed) { if $0 { nav.back() } }
        // Back from a challenge run: the attempt has a result now.
        .onReturn { model.vm.refresh() }
    }

    private func content(_ detail: ChallengeDetail, joining: Bool) -> some View {
        let c = detail.challenge
        let closesIn = IosSupport.shared.closesIn(c: c)
        return List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text(c.title).font(.title.bold())
                    Text("\(c.status.uppercased()) • \(closesIn)").foregroundStyle(OsirisColor.faint)
                }
            }
            if let route = detail.course?.route, route.count >= 2 {
                Section {
                    RunMap(course: detail.course, preview: true)
                        .frame(height: 200)
                        .listRowInsets(EdgeInsets())
                        .accessibilityLabel("Course map")
                }
            }
            Section("TERMS") {
                TermRow(label: "Course distance", value: Format.shared.distance(metres: c.courseDistanceM))
                TermRow(label: "Time to beat", value: Format.shared.duration(seconds: c.targetSeconds))
                if let closes = IosSupport.shared.closesAtLocal(c: c) { TermRow(label: "Closes", value: "\(closes) (\(closesIn))") }
                TermRow(label: "Entry cost", value: c.entryCrystals == 0 ? "Free" : "\(c.entryCrystals) crystals")
                TermRow(label: "Reward", value: "+\(c.winXp) XP for a win, +\(c.participationXp) XP for a verified finish")
                TermRow(label: "Attempts so far", value: "\(c.attemptCount)")
                Text("Privacy: the map shows only an approximate area. The exact route is shared "
                     + "with players who join. Results are shown without names.")
                    .font(.caption).foregroundStyle(OsirisColor.faint)
            }
            if let notes = c.safetyNotes, !notes.trimmingCharacters(in: .whitespaces).isEmpty {
                Section {
                    Label {
                        VStack(alignment: .leading) {
                            Text("Safety notes")
                            Text(notes).font(.subheadline).foregroundStyle(OsirisColor.muted)
                        }
                    } icon: { Image(systemName: "cross.case.fill").foregroundStyle(OsirisColor.warning) }
                }
                .listRowBackground(OsirisColor.warning.opacity(0.12))
            }
            if let attempt = c.myAttempt { Section { attemptCard(attempt) } }
            Section { action(c, joining: joining) }
                .listRowBackground(Color.clear)
        }
        .refreshable { model.vm.refresh() }
    }

    @ViewBuilder private func action(_ c: ChallengeSummary, joining: Bool) -> some View {
        if c.isMine {
            Text("This is your challenge. You earn XP each time a challenger fails to beat your time.")
                .foregroundStyle(OsirisColor.faint).multilineTextAlignment(.center).frame(maxWidth: .infinity)
        } else if c.canJoin {
            Button { model.vm.join() } label: {
                Label(joining ? "JOINING…" : "JOIN CHALLENGE", systemImage: "person.fill.checkmark").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(joining)
        } else if c.canRun {
            Button { nav.open(.run(challengeId: c.id)) } label: {
                Label(c.myAttempt?.status == "rejected" ? "TRY AGAIN" : "RUN THIS COURSE", systemImage: "figure.run").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
        }
    }

    private func attemptCard(_ a: AttemptSummary) -> some View {
        let color: Color = a.outcome == "won" ? OsirisColor.success : (a.status == "rejected" ? OsirisColor.error : OsirisColor.secondary)
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("YOUR ATTEMPT").fontWeight(.bold).kerning(1.5)
                Spacer()
                Text(a.label).fontWeight(.bold).foregroundStyle(color)
            }
            if let elapsed = a.elapsedSeconds?.doubleValue, elapsed > 0 {
                TermRow(label: "Your time", value: Format.shared.duration(seconds: elapsed))
            }
            if let coverage = a.courseCoverage?.doubleValue {
                TermRow(label: "On course", value: "\(Int((coverage * 100).rounded()))%")
            }
            if a.xpAwarded > 0 { TermRow(label: "XP earned", value: "+\(a.xpAwarded)") }
            if a.status == "accepted" && (a.outcome == "won" || a.outcome == "lost") {
                HStack {
                    Spacer()
                    Button {
                        Task { @MainActor in
                            if let text = try? await model.vm.shareResult(attemptId: a.id) { shareText = SharedText(text: text) }
                        }
                    } label: { Label("SHARE RESULT", systemImage: "square.and.arrow.up") }
                    .buttonStyle(.borderless)
                }
            }
            ForEach(a.reasonCodes, id: \.self) { code in
                Text("• \(ReasonCopy.shared.explain(code: code))").foregroundStyle(OsirisColor.muted)
            }
        }
    }
}
