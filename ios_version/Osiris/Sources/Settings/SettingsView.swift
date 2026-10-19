import SwiftUI
import OsirisShared

/// Profile, privacy switches, invites, safety, data export, sign-out and account erasure, from
/// the shared SettingsViewModel. Erasing takes two steps: a warning, then the password.
struct SettingsView: View {
    @StateObject private var model: Observed<SettingsViewModel, SettingsState>
    @State private var sheet: SettingsSheet?
    @State private var editingName = false
    @State private var editingCity = false
    @State private var consenting = false
    @State private var withdrawing = false
    @State private var erasing = false
    @State private var confirmingErase = false
    @State private var text = ""
    @State private var password = ""

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.settings()) { $0.state })
    }

    private var vm: SettingsViewModel { model.vm }

    var body: some View {
        let s = model.state
        LoadableContent(state: s.profile, onRetry: { vm.refresh() }) { (p: PlayerProfile) in
            settings(p, s)
        }
        .background(OsirisColor.background)
        .navigationTitle("SETTINGS")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
        .shareSheet(s.share) { vm.shared(completed: $0) }
        .sheet(item: $sheet) { which in
            switch which {
            case .goal: GoalSheet(current: currentGoal(s)) { goal in vm.setGoal(goal: goal); sheet = nil }
            case .blocks: BlocksSheet(model: model)
            case .rules: RulesSheet(rules: model.state.rules)
            }
        }
        .exerciseConsentSheet(isPresented: $consenting) { allow in
            if allow { vm.setExerciseConsent(granted: true, deleteData: false) }
        }
        .withdrawExerciseConsentAlert(
            isPresented: $withdrawing,
            onKeep: { vm.setExerciseConsent(granted: false, deleteData: false) },
            onDelete: { vm.setExerciseConsent(granted: false, deleteData: true) }
        )
        .textInputAlert(
            "Your name", isPresented: $editingName, label: "Name", text: $text,
            confirm: "SAVE", dismiss: "CANCEL",
            onConfirm: { vm.setDisplayName(name: String($0.prefix(30))) }, onDismiss: {}
        )
        .textInputAlert(
            "Home city", isPresented: $editingCity, label: "City, e.g. Bedford NS", text: $text,
            confirm: "SAVE", dismiss: "CANCEL",
            onConfirm: { vm.setCity(city: $0) }, onDismiss: {}
        )
        .alert("Erase your account?", isPresented: $erasing) {
            Button("ERASE", role: .destructive) {
                password = ""
                confirmingErase = true
            }
            Button("KEEP MY ACCOUNT", role: .cancel) {}
        } message: {
            Text("This deletes your routes, runs, badges, and profile. It cannot be undone. Other players keep their own results.")
        }
        .textInputAlert(
            "Confirm with your password", isPresented: $confirmingErase, label: "Password", text: $password,
            confirm: "ERASE", dismiss: "CANCEL", secure: true, destructive: true,
            onConfirm: { typed in
                let value = String(typed.prefix(128))
                password = ""
                if !value.isEmpty { vm.erase(password: value) }
            },
            onDismiss: { password = "" }
        )
    }

    private func currentGoal(_ s: SettingsState) -> Goal {
        Goal.companion.fromWire(value: (s.profile.valueOrNull as? PlayerProfile)?.goal ?? Goal.fitness.wire)
    }

    private func settings(_ p: PlayerProfile, _ s: SettingsState) -> some View {
        List {
            Section(header: header("Profile")) {
                row("person.text.rectangle", p.displayName, "Name others see") {
                    text = p.displayName
                    editingName = true
                }
                row("flag.circle", Goal.companion.fromWire(value: p.goal).label, s.identityLine) { sheet = .goal }
                row("building.2", p.city ?? "Not set", "Home city, used for local rankings (never from GPS)") {
                    text = p.city ?? ""
                    editingCity = true
                }
            }
            Section(header: header("Privacy")) {
                toggle("Location during runs", "Needed to record and verify runs", p.locationConsent) { vm.setLocationConsent(on: $0) }
                toggle("Show my name on leaderboards", "When off, you appear as \"Private runner\"", p.leaderboardOptIn) {
                    vm.setLeaderboardOptIn(on: $0)
                }
                toggle("Public achievement page", "Shows your rank, runs, and badges. Never your location.", p.publicProfile) {
                    vm.setPublicProfile(on: $0)
                }
                toggle("Camera exercise counting", "Counts reps on this phone; keeps rep counts and timings", s.exerciseConsent) { on in
                    if on { consenting = true } else { withdrawing = true }
                }
            }
            Section(header: header("Invite friends")) { invite(s.referral) }
            Section(header: header("Safety")) {
                row("nosign", "Blocked players") {
                    vm.loadBlocks()
                    sheet = .blocks
                }
                row("list.bullet.clipboard", "Rules, rewards, and verification") {
                    vm.loadRules()
                    sheet = .rules
                }
            }
            Section(header: header("Account")) {
                row("laptopcomputer.and.iphone", "Sign out of all other devices") { vm.signOutEverywhere() }
                row("square.and.arrow.down", "Download my data") { vm.exportData() }
                row("rectangle.portrait.and.arrow.right", "Log out") { vm.logout() }
                row("trash", "Erase my account", color: OsirisColor.error) { erasing = true }
                    .disabled(s.busy)
            }
        }
    }

    @ViewBuilder
    private func invite(_ referral: any Loadable) -> some View {
        if let r = referral.valueOrNull as? ReferralSummary {
            HStack {
                Image(systemName: "person.badge.plus")
                VStack(alignment: .leading) {
                    Text("Your invite code: \(r.code)")
                    Text("\(r.rewarded) friends rewarded  •  \(r.pending) waiting for their first run")
                        .font(.subheadline).foregroundStyle(OsirisColor.muted)
                }
                Spacer()
                Button { vm.shareInvite() } label: { Image(systemName: "doc.on.doc") }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Share invite link")
            }
            ForEach(r.rules, id: \.self) { rule in
                Text(rule).font(.caption).foregroundStyle(OsirisColor.faint)
            }
        } else if let failed = referral as? LoadableFailed {
            Text(failed.message)
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }

    private func header(_ text: String) -> some View {
        Text(text.uppercased()).font(.caption).kerning(1.2).foregroundStyle(OsirisColor.secondary)
    }

    private func row(_ icon: String, _ title: String, _ subtitle: String? = nil, color: Color = .white, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label {
                VStack(alignment: .leading) {
                    Text(title).foregroundStyle(color)
                    if let subtitle, !subtitle.isEmpty {
                        Text(subtitle).font(.subheadline).foregroundStyle(OsirisColor.muted)
                    }
                }
            } icon: { Image(systemName: icon).foregroundStyle(color) }
        }
    }

    private func toggle(_ title: String, _ subtitle: String, _ on: Bool, _ change: @escaping (Bool) -> Void) -> some View {
        Toggle(isOn: Binding(get: { on }, set: change)) {
            VStack(alignment: .leading) {
                Text(title)
                Text(subtitle).font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
        }
    }
}

private enum SettingsSheet: String, Identifiable {
    case goal, blocks, rules
    var id: String { rawValue }
}

private struct GoalSheet: View {
    let current: Goal
    let onPick: (Goal) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(Goal.entries, id: \.wire) { g in
                Button { onPick(g) } label: {
                    VStack(alignment: .leading) {
                        Text(g.label).foregroundStyle(g == current ? OsirisColor.secondary : .white)
                        Text(g.description_).font(.subheadline).foregroundStyle(OsirisColor.muted)
                    }
                }
            }
            .navigationTitle("Your goal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("CANCEL") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }
}

private struct BlocksSheet: View {
    @ObservedObject var model: Observed<SettingsViewModel, SettingsState>

    var body: some View {
        NavigationStack {
            Group {
                if let blocks = model.state.blocks {
                    if blocks.isEmpty {
                        Text("You haven't blocked anyone.").frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List(blocks, id: \.id) { b in
                            HStack {
                                Text(b.name)
                                Spacer()
                                Button("UNBLOCK") { model.vm.unblock(id: b.id) }.buttonStyle(.borderless)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .navigationTitle("Blocked players")
            .navigationBarTitleDisplayMode(.inline)
            .messages(model)
        }
        .presentationDetents([.medium, .large])
    }
}

private struct RulesSheet: View {
    let rules: [RulesSection]?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    if rules == nil { ProgressView().frame(maxWidth: .infinity).padding(12) }
                    ForEach(rules ?? [], id: \.title) { section in
                        Text(section.title).font(.headline).padding(.top, 16)
                        ForEach(section.lines, id: \.self) { line in
                            Text("•  \(line)").padding(.vertical, 4)
                        }
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .navigationTitle("RULES")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
