import SwiftUI
import OsirisShared

/// Home screen: today's quest, the week, tomorrow, a nearby starter challenge and the way to
/// every other screen, from the shared TodayViewModel.
struct TodayView: View {
    @StateObject private var model: Observed<TodayViewModel, any Loadable>
    @StateObject private var location = LocationTracker()
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.today()) { $0.state })
    }

    var body: some View {
        LoadableContent(state: model.state, onRetry: { model.vm.refresh() }) { (t: TodayData) in
            today(t)
        }
        .background(OsirisColor.background)
        .navigationTitle("OSIRIS")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { nav.open(.settings) } label: { Image(systemName: "gearshape") }
                    .accessibilityLabel("Settings")
            }
        }
        .messages(model)
        // One position for the nearby starter challenge; without permission the suggestion is skipped.
        .task {
            if let p = await location.currentPosition(askIfNeeded: false) {
                model.vm.onPosition(position: p)
            } else {
                model.vm.onNoPosition()
            }
        }
        // Back from a run or another screen: the quest progress may have moved.
        .onReturn { model.vm.refresh() }
    }

    private func today(_ t: TodayData) -> some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Hi \(t.displayName)").font(.title2.bold())
                    Text("\(t.performanceRank) \(t.identity)  •  \(t.xp) XP").foregroundStyle(OsirisColor.muted)
                }
            }
            if t.needsLocationConsent {
                Section {
                    HStack {
                        Image(systemName: "location")
                        VStack(alignment: .leading) {
                            Text("Allow location during runs")
                            Text("Needed to verify your distance. Your route is never shown to others.")
                                .font(.subheadline).foregroundStyle(OsirisColor.muted)
                        }
                        Spacer()
                        Button("ALLOW") { model.vm.grantLocationConsent() }
                    }
                }
                .listRowBackground(OsirisColor.secondary.opacity(0.15))
            }
            Section { quest(t.today) }
            Section { week(t.week, streakWeeks: t.streakWeeks) }
            Section {
                Label {
                    VStack(alignment: .leading) {
                        Text("Tomorrow")
                        Text(t.tomorrow.title).font(.subheadline).foregroundStyle(OsirisColor.muted)
                    }
                } icon: { Image(systemName: "sunrise").foregroundStyle(OsirisColor.secondary) }
            }
            if let c = t.starterChallenge {
                Section {
                    Button { nav.open(.challenge(c.id)) } label: { starter(c) }
                }
            }
            Section { NavGrid(open: nav.open) }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
            Section {
                Label(t.safetyNote, systemImage: "cross.case").font(.caption).foregroundStyle(OsirisColor.faint)
                Text(t.tagline).font(.caption).foregroundStyle(OsirisColor.faint).frame(maxWidth: .infinity)
            }
            .listRowBackground(Color.clear)
        }
        .refreshable { model.vm.refresh() }
    }

    private func quest(_ q: Quest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(q.heading.uppercased())
                Spacer()
                Text("+\(q.xp) XP")
            }
            .font(FrostFont.mono(.caption))
            .foregroundStyle(OsirisColor.muted)
            // The screen's focal point: today's quest distance, at hero size; everything else recedes.
            HeroMetric(
                value: Format.shared.fixed(value: q.progressM / 1000, decimals: 2),
                unit: "/ \(Format.shared.km(metres: Double(q.targetM)))"
            )
            Text("\(q.title). \(q.description_)").font(FrostFont.manrope(.callout)).foregroundStyle(OsirisColor.muted)
            ProgressView(value: q.fraction).padding(.top, 8)
            if q.completed {
                HStack {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(OsirisColor.success)
                    Text(q.rewarded ? "Done. +\(q.xp) XP earned." : "Done!")
                    Spacer()
                    Button("GO AGAIN", action: startRun)
                }
                .padding(.top, 8)
            } else {
                Button(action: startRun) {
                    Label(q.optional ? "START (OPTIONAL)" : "START", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .padding(.top, 8)
            }
        }
        .padding(.vertical, 6)
        // Two buttons in one list row: only the buttons themselves should react.
        .buttonStyle(.borderless)
    }

    private func startRun() {
        model.vm.onStartQuest()
        nav.open(.run(challengeId: nil))
    }

    private func week(_ w: WeeklyGoal, streakWeeks: Int32) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                SectionLabel(text: "This week")
                Spacer()
                Image(systemName: "flame.fill").foregroundStyle(streakWeeks > 0 ? OsirisColor.warning : .white.opacity(0.24))
                Text(streakWeeks == 1 ? "1 week streak" : "\(streakWeeks) week streak")
            }
            HStack(spacing: 8) {
                ForEach(0..<Int(w.activeDaysTarget), id: \.self) { i in
                    let done = i < Int(w.activeDays)
                    Image(systemName: done ? "circle.fill" : "circle")
                        .foregroundStyle(done ? OsirisColor.secondary : .white.opacity(0.38))
                }
                Spacer()
                Text(Format.shared.km(metres: w.distanceM)).foregroundStyle(OsirisColor.muted)
            }
            .accessibilityElement(children: .combine)
            Text(w.completed
                 ? "Weekly goal met. Enjoy your rest days."
                 : "\(w.activeDays) of \(w.activeDaysTarget) active days. Rest days never break your streak.")
                .font(.footnote).foregroundStyle(OsirisColor.muted)
        }
        .padding(.vertical, 6)
    }

    private func starter(_ c: StarterChallenge) -> some View {
        let away = c.distanceKm.map { "  •  about \(Format.shared.fixed(value: $0.doubleValue, decimals: 1)) km away" } ?? ""
        return HStack {
            Image(systemName: "flag").foregroundStyle(OsirisColor.primary)
            VStack(alignment: .leading) {
                Text(c.title)
                Text("\(Format.shared.fixed(value: c.courseDistanceM / 1000, decimals: 1)) km course\(away)  •  free")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(OsirisColor.faint)
        }
    }
}

/// Three tiles a row: screens without a tab of their own.
private struct NavGrid: View {
    let open: (Route) -> Void

    private let items: [(icon: String, label: String, route: Route)] = [
        ("person.3", "Clubs", .clubs),
        ("dumbbell", "Bodyweight", .exercises),
        ("point.topleft.down.curvedto.point.bottomright.up", "My courses", .courses),
        ("person.badge.plus", "Invite", .settings),
    ]

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
            ForEach(items, id: \.label) { item in
                Button { open(item.route) } label: {
                    VStack(spacing: 6) {
                        Image(systemName: item.icon).foregroundStyle(OsirisColor.secondary)
                        Text(item.label).font(.footnote)
                    }
                    .frame(maxWidth: .infinity, minHeight: 84)
                    .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
            }
        }
    }
}
