import SwiftUI
import OsirisShared

/// Redesigned Osiris Home Screen:
/// 1. Top-right Notifications icon (feature suggestions, app updates, social follows/reactions/comments)
/// 2. Suggested Challenges Circular-Floating Card Deck (global challenges joinable from anywhere)
/// 3. Streak Start & Camera-Verified Workout Customizer (e.g. Push-ups — 10 × 3, 16 AI exercises)
/// 4. Today's Quest, Weekly Streak strip, Tomorrow & Shortcuts
/// 5. Suggested Osirians horizontal carousel (Follow, '×' dismiss, "See All" trending sheet)
/// 6. People's Posts social feed (workouts, claimed domains, streaks, Mana Crystals, react, comment, share)
struct TodayView: View {
    @StateObject private var model: Observed<TodayViewModel, HomeScreenState>
    @StateObject private var location = LocationTracker()
    @EnvironmentObject private var nav: Navigator

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.today()) { $0.home })
    }

    private var vm: TodayViewModel { model.vm }

    var body: some View {
        let home = model.state
        LoadableContent(state: home.today, onRetry: { vm.refresh() }) { (t: TodayData) in
            today(t, home: home)
        }
        .background(OsirisColor.background)
        .navigationTitle("Osiris")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 12) {
                    Button { vm.openNotifications(open: true) } label: {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: home.unreadNotifications > 0 ? "bell.badge.fill" : "bell")
                                .foregroundStyle(home.unreadNotifications > 0 ? OsirisColor.secondary : .white)
                        }
                    }
                    .accessibilityLabel("Notifications")

                    Button { nav.open(.settings) } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings")
                }
            }
        }
        .messages(model)
        .shareSheet(home.share) { vm.shared(completed: $0) }
        .sheet(isPresented: Binding(get: { home.notificationsOpen }, set: { vm.openNotifications(open: $0) })) {
            NotificationsSheetView(
                notifications: home.notifications,
                onMarkRead: { vm.markNotificationRead(id: $0) },
                onMarkAllRead: { vm.markAllNotificationsRead() },
                onNavigate: { route in
                    vm.openNotifications(open: false)
                    switch route {
                    case "exercise": nav.open(.exercises)
                    case "challenges": nav.open(.challenges)
                    case "communities": nav.open(.clubs)
                    default: break
                    }
                }
            )
        }
        .sheet(isPresented: Binding(get: { home.workoutCustomizerOpen }, set: { vm.openWorkoutCustomizer(open: $0) })) {
            WorkoutCustomizerSheetView(
                plan: home.workoutPlan,
                onSelectOption: { vm.selectWorkoutOption(key: $0) },
                onSetReps: { vm.setWorkoutReps(reps: Int32($0)) },
                onSetSets: { vm.setWorkoutSets(sets: Int32($0)) },
                onSetHoldSeconds: { vm.setWorkoutHoldSeconds(seconds: Int32($0)) },
                onSetDistanceKm: { vm.setWorkoutDistanceKm(km: $0) },
                onStart: {
                    vm.openWorkoutCustomizer(open: false)
                    startWorkoutPlan(home.workoutPlan)
                }
            )
        }
        .sheet(isPresented: Binding(get: { home.trendingSheetOpen }, set: { vm.openTrendingOsirians(open: $0) })) {
            TrendingOsiriansSheetView(
                osirians: home.trendingOsirians,
                onFollowToggle: { p in
                    if p.following { vm.unfollowOsirian(userId: p.userId) } else { vm.followOsirian(userId: p.userId) }
                }
            )
        }
        .sheet(isPresented: Binding(get: { home.postComposerOpen }, set: { vm.openPostComposer(open: $0) })) {
            PostComposerSheetView(
                plan: home.workoutPlan,
                streakWeeks: (home.today.valueOrNull as? TodayData)?.streakWeeks ?? 1,
                onPublish: { vm.publishPost(draft: $0) }
            )
        }
        .sheet(
            isPresented: Binding(
                get: { home.activeCommentsPostId != nil },
                set: { if !$0 { vm.openComments(postId: nil) } }
            )
        ) {
            if let postId = home.activeCommentsPostId?.int32Value {
                CommentsSheetView(
                    comments: home.activePostComments,
                    onAddComment: { vm.addComment(postId: postId, body: $0) }
                )
            }
        }
        .task {
            if let p = await location.currentPosition(askIfNeeded: false) {
                vm.onPosition(position: p)
            } else {
                vm.onNoPosition()
            }
        }
        .onReturn { vm.refresh() }
    }

    private func startWorkoutPlan(_ plan: WorkoutPlan) {
        if plan.option.isCameraExercise {
            nav.open(.exercisePlan(
                key: plan.optionKey,
                sets: plan.sets,
                reps: plan.repsPerSet,
                holdS: plan.holdSecondsPerSet
            ))
        } else {
            vm.onStartQuest()
            nav.open(.run(challengeId: nil))
        }
    }

    private func today(_ t: TodayData, home: HomeScreenState) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Hi \(t.displayName)").font(.manrope(.title2).bold())
                    Text("\(t.performanceRank) \(t.identity)  •  \(t.xp) XP").foregroundStyle(OsirisColor.muted)
                }

                if t.needsLocationConsent {
                    HStack {
                        Image(systemName: "location")
                        VStack(alignment: .leading) {
                            Text("Allow location during runs")
                            Text("Needed to verify your distance. Your route is never shown to others.")
                                .font(.manrope(.subheadline)).foregroundStyle(OsirisColor.muted)
                        }
                        Spacer()
                        Button("Allow") { vm.grantLocationConsent() }
                    }
                    .padding(14)
                    .background(OsirisColor.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 14))
                }

                // 1. Suggested Global Challenges Circular-Floating Card Deck
                if !home.suggestedChallenges.isEmpty {
                    suggestedChallengesDeck(home.suggestedChallenges, joiningId: home.joiningChallengeId?.int32Value)
                }

                // 2. Streak Start & Workout Customizer Card (e.g. Push-ups — 10 × 3)
                streakStartCard(streakWeeks: t.streakWeeks, plan: home.workoutPlan)

                // 3. Preserved Today Sections
                quest(t.today)
                week(t.week, streakWeeks: t.streakWeeks)
                HStack {
                    Image(systemName: "sunrise").foregroundStyle(OsirisColor.secondary)
                    VStack(alignment: .leading) {
                        Text("Tomorrow").font(.manrope(.caption)).foregroundStyle(OsirisColor.muted)
                        Text(t.tomorrow.title).font(.manrope(.subheadline).bold())
                    }
                    Spacer()
                }
                .padding(14)
                .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 14))

                if let c = t.starterChallenge {
                    Button { nav.open(.challenge(c.id)) } label: { starter(c) }
                        .padding(14)
                        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 14))
                }

                NavGrid(open: nav.open)

                // 4. Suggested Osirians Carousel
                suggestedOsiriansSection(home.suggestedOsirians)

                // 5. People's Posts Social Feed
                peoplesPostsSection(home.feedPosts)

                VStack(spacing: 6) {
                    Label(t.safetyNote, systemImage: "cross.case").font(.manrope(.caption)).foregroundStyle(OsirisColor.faint)
                    Text(t.tagline).font(.manrope(.caption)).foregroundStyle(OsirisColor.faint).frame(maxWidth: .infinity)
                }
                .padding(.top, 8)
            }
            .padding(20)
        }
        .refreshable { vm.refresh() }
    }

    private func suggestedChallengesDeck(_ challenges: [SuggestedChallenge], joiningId: Int32?) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "globe").foregroundStyle(OsirisColor.secondary)
                Text("Suggested Challenges").font(.manrope(.headline))
                Spacer()
                Text("Global Deck").font(.manrope(.caption)).foregroundStyle(OsirisColor.secondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    ForEach(challenges, id: \.id) { c in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("GLOBAL · \(c.distanceLabel)")
                                    .font(.manrope(.caption2).bold())
                                    .foregroundStyle(OsirisColor.secondary)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(OsirisColor.secondary.opacity(0.18), in: RoundedRectangle(cornerRadius: 8))
                                Spacer()
                                Text("+\(c.winXp) XP · \(c.participants) joined")
                                    .font(.manrope(.caption2))
                                    .foregroundStyle(OsirisColor.muted)
                            }
                            Text(c.title)
                                .font(.manrope(.headline))
                                .lineLimit(1)
                            Text(c.description_)
                                .font(.manrope(.subheadline))
                                .foregroundStyle(OsirisColor.muted)
                                .lineLimit(1)
                            if c.joined {
                                Button {
                                    vm.onStartQuest()
                                    nav.open(.run(challengeId: c.id))
                                } label: {
                                    Label("Joined · Start Challenge", systemImage: "checkmark.circle.fill")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.raised)
                            } else {
                                Button {
                                    vm.joinSuggestedChallenge(challengeId: c.id)
                                } label: {
                                    Text(joiningId == c.id ? "Joining…" : "Join Challenge")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.key)
                                .disabled(joiningId == c.id)
                            }
                        }
                        .padding(16)
                        .frame(width: 292)
                        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 18))
                        .overlay(
                            RoundedRectangle(cornerRadius: 18)
                                .stroke(OsirisColor.primary.opacity(0.35), lineWidth: 1)
                        )
                    }
                }
            }
        }
    }

    private func streakStartCard(streakWeeks: Int32, plan: WorkoutPlan) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "flame.fill").foregroundStyle(OsirisColor.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(streakWeeks > 0 ? "Streak Start · \(streakWeeks)w Active" : "Streak Start Workout")
                        .font(.manrope(.headline))
                    Text(plan.badgeLabel).font(.manrope(.caption2)).foregroundStyle(OsirisColor.secondary)
                }
                Spacer()
                Button("Customize") { vm.openWorkoutCustomizer(open: true) }
                    .buttonStyle(.raised)
            }
            HStack(spacing: 10) {
                Image(systemName: plan.option.isCameraExercise ? exerciseIcon(plan.optionKey) : "figure.run")
                    .foregroundStyle(OsirisColor.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.measureLabel).font(.manrope(.subheadline).bold())
                    Text(plan.option.isCameraExercise
                         ? "On-device Vision Neural Engine pose & rep verification"
                         : "GPS-verified route & territory tracking")
                        .font(.manrope(.caption2))
                        .foregroundStyle(OsirisColor.muted)
                }
                Spacer()
            }
            .padding(12)
            .background(OsirisColor.background.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))

            Button {
                startWorkoutPlan(plan)
            } label: {
                Label("Start \(plan.measureLabel)", systemImage: plan.option.isCameraExercise ? "video.fill" : "play.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.key)
        }
        .padding(16)
        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 18))
    }

    private func suggestedOsiriansSection(_ osirians: [SuggestedOsirian]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Suggested Osirians").font(.manrope(.headline))
                    Text("Trending athletes & domain holders").font(.manrope(.caption)).foregroundStyle(OsirisColor.faint)
                }
                Spacer()
                Button("See All") { vm.openTrendingOsirians(open: true) }
                    .font(.manrope(.subheadline).bold())
                    .foregroundStyle(OsirisColor.primary)
            }
            if osirians.isEmpty {
                Text("No more suggestions. Tap See All for trending Osirians.")
                    .font(.manrope(.footnote))
                    .foregroundStyle(OsirisColor.muted)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(osirians, id: \.userId) { person in
                            VStack(spacing: 6) {
                                HStack {
                                    Spacer()
                                    Button {
                                        vm.dismissOsirian(userId: person.userId)
                                    } label: {
                                        Image(systemName: "xmark")
                                            .font(.caption2)
                                            .foregroundStyle(OsirisColor.faint)
                                    }
                                    .accessibilityLabel("Dismiss \(person.displayName)")
                                }
                                Circle()
                                    .fill(OsirisColor.primary.opacity(0.2))
                                    .frame(width: 52, height: 52)
                                    .overlay(Text(person.initials).font(.manrope(.subheadline).bold()).foregroundStyle(OsirisColor.secondary))
                                Text(person.displayName).font(.manrope(.subheadline).bold()).lineLimit(1)
                                Text("\(person.rank) · \(person.title)").font(.manrope(.caption2)).foregroundStyle(OsirisColor.secondary).lineLimit(1)
                                Text(person.trendingReason).font(.manrope(.caption2)).foregroundStyle(OsirisColor.faint).lineLimit(1)
                                Button {
                                    if person.following {
                                        vm.unfollowOsirian(userId: person.userId)
                                    } else {
                                        vm.followOsirian(userId: person.userId)
                                    }
                                } label: {
                                    Text(person.following ? "Following" : "Follow").frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.key)
                            }
                            .padding(12)
                            .frame(width: 162)
                            .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 14))
                        }
                    }
                }
            }
        }
    }

    private func peoplesPostsSection(_ posts: [FeedPost]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("People's Posts").font(.manrope(.headline))
                    Text("Workouts, domains, streaks & Mana Crystals").font(.manrope(.caption)).foregroundStyle(OsirisColor.faint)
                }
                Spacer()
                Button("+ Post") { vm.openPostComposer(open: true) }
                    .buttonStyle(.raised)
            }
            ForEach(posts, id: \.id) { post in
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        Circle()
                            .fill(OsirisColor.primary.opacity(0.2))
                            .frame(width: 40, height: 40)
                            .overlay(Text(post.authorInitials).font(.manrope(.caption).bold()).foregroundStyle(OsirisColor.secondary))
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(post.authorName).font(.manrope(.subheadline).bold())
                                Text("\(post.authorRank) · \(post.authorTitle)").font(.manrope(.caption2)).foregroundStyle(OsirisColor.secondary)
                            }
                            Text("@\(post.authorHandle) • \(post.kindBadgeLabel)").font(.manrope(.caption2)).foregroundStyle(OsirisColor.faint)
                        }
                        Spacer()
                    }
                    if let measure = post.summary.measureLabel, !measure.isEmpty {
                        HStack {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(OsirisColor.secondary)
                            Text(measure).font(.manrope(.subheadline).bold())
                            Spacer()
                            if post.summary.xpEarned > 0 {
                                Text("+\(post.summary.xpEarned) XP").font(.manrope(.caption2)).foregroundStyle(OsirisColor.secondary)
                            }
                        }
                        .padding(10)
                        .background(OsirisColor.primary.opacity(0.14), in: RoundedRectangle(cornerRadius: 10))
                    }
                    if !post.caption.isEmpty {
                        Text(post.caption).font(.manrope(.body))
                    }
                    HStack(spacing: 8) {
                        ForEach([("fire", "🔥"), ("like", "❤️"), ("clap", "👏"), ("crown", "👑")], id: \.0) { key, emoji in
                            let count = post.reactionCount(type: key)
                            Button {
                                vm.reactToPost(postId: post.id, reaction: key)
                            } label: {
                                Text(count > 0 ? "\(emoji) \(count)" : emoji)
                                    .font(.manrope(.caption))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(
                                        (post.myReaction == key ? OsirisColor.primary.opacity(0.3) : OsirisColor.background.opacity(0.5)),
                                        in: RoundedRectangle(cornerRadius: 12)
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                        Button {
                            vm.openComments(postId: KotlinInt(int: post.id))
                        } label: {
                            Label("\(post.commentCount)", systemImage: "bubble.right").font(.manrope(.caption))
                        }
                        .buttonStyle(.plain)
                        Button {
                            vm.sharePost(postId: post.id)
                        } label: {
                            Label(post.shareCount > 0 ? "\(post.shareCount)" : "Share", systemImage: "square.and.arrow.up")
                                .font(.manrope(.caption))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(16)
                .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 16))
            }
        }
    }

    private func quest(_ q: Quest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(q.heading)
                Spacer()
                Text("+\(q.xp) XP")
            }
            .font(FrostFont.manrope(.caption))
            .foregroundStyle(OsirisColor.muted)
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
                    Button("Go again", action: startRun)
                }
                .padding(.top, 8)
            } else {
                Button(action: startRun) {
                    Label(q.optional ? "Start (optional)" : "Start", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.key)
                .padding(.top, 8)
            }
        }
        .padding(16)
        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 18))
    }

    private func startRun() {
        vm.onStartQuest()
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
                .font(.manrope(.footnote)).foregroundStyle(OsirisColor.muted)
        }
        .padding(14)
        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func starter(_ c: StarterChallenge) -> some View {
        let away = c.distanceKm.map { "  •  about \(Format.shared.fixed(value: $0.doubleValue, decimals: 1)) km away" } ?? ""
        return HStack {
            Image(systemName: "flag").foregroundStyle(OsirisColor.primary)
            VStack(alignment: .leading) {
                Text(c.title)
                Text("\(Format.shared.fixed(value: c.courseDistanceM / 1000, decimals: 1)) km course\(away)  •  free")
                    .font(.manrope(.subheadline)).foregroundStyle(OsirisColor.muted)
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
                        Text(item.label).font(.manrope(.footnote))
                    }
                    .frame(maxWidth: .infinity, minHeight: 84)
                    .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private struct NotificationsSheetView: View {
    let notifications: [NotificationItem]
    let onMarkRead: (Int32) -> Void
    let onMarkAllRead: () -> Void
    let onNavigate: (String) -> Void

    var body: some View {
        NavigationStack {
            List {
                ForEach(notifications, id: \.id) { n in
                    Button {
                        if !n.read { onMarkRead(n.id) }
                        if let route = n.actionRoute, !route.isEmpty { onNavigate(route) }
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(n.title).font(.manrope(.subheadline).weight(n.read ? .regular : .bold))
                                Spacer()
                                if !n.read { Circle().fill(OsirisColor.secondary).frame(width: 8, height: 8) }
                            }
                            Text(n.body).font(.manrope(.footnote)).foregroundStyle(OsirisColor.muted)
                        }
                    }
                }
            }
            .navigationTitle("Notifications")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Mark all read", action: onMarkAllRead)
                }
            }
        }
    }
}

private struct WorkoutCustomizerSheetView: View {
    let plan: WorkoutPlan
    let onSelectOption: (String) -> Void
    let onSetReps: (Int) -> Void
    let onSetSets: (Int) -> Void
    let onSetHoldSeconds: (Int) -> Void
    let onSetDistanceKm: (Double) -> Void
    let onStart: () -> Void

    var body: some View {
        NavigationStack {
            List {
                Section(header: Text("1. Select Workout / Camera-Verified Exercise")) {
                    ForEach(WorkoutPlan.companion.WORKOUT_OPTIONS, id: \.key) { opt in
                        Button {
                            onSelectOption(opt.key)
                        } label: {
                            HStack {
                                Text("\(opt.name) (\(opt.category))")
                                Spacer()
                                if plan.optionKey == opt.key {
                                    Image(systemName: "checkmark").foregroundStyle(OsirisColor.secondary)
                                }
                            }
                        }
                    }
                }
                Section(header: Text("2. Customize Measure (\(plan.measureLabel))")) {
                    if !plan.option.isCameraExercise {
                        Stepper("Distance: \(Format.shared.fixed(value: plan.targetDistanceKm, decimals: 1)) km", onIncrement: {
                            onSetDistanceKm(plan.targetDistanceKm + 0.5)
                        }, onDecrement: {
                            onSetDistanceKm(plan.targetDistanceKm - 0.5)
                        })
                    } else if plan.option.isHold {
                        Stepper("Hold: \(plan.holdSecondsPerSet)s per set", onIncrement: {
                            onSetHoldSeconds(Int(plan.holdSecondsPerSet) + 15)
                        }, onDecrement: {
                            onSetHoldSeconds(Int(plan.holdSecondsPerSet) - 15)
                        })
                        Stepper("Sets: \(plan.sets)", onIncrement: {
                            onSetSets(Int(plan.sets) + 1)
                        }, onDecrement: {
                            onSetSets(Int(plan.sets) - 1)
                        })
                    } else {
                        Stepper("Reps per set: \(plan.repsPerSet)", onIncrement: {
                            onSetReps(Int(plan.repsPerSet) + 1)
                        }, onDecrement: {
                            onSetReps(Int(plan.repsPerSet) - 1)
                        })
                        Stepper("Sets: \(plan.sets)", onIncrement: {
                            onSetSets(Int(plan.sets) + 1)
                        }, onDecrement: {
                            onSetSets(Int(plan.sets) - 1)
                        })
                    }
                }
                Section {
                    Button(action: onStart) {
                        Text("Start \(plan.measureLabel)").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.key)
                }
            }
            .navigationTitle("Customize Workout")
        }
    }
}

private struct TrendingOsiriansSheetView: View {
    let osirians: [SuggestedOsirian]
    let onFollowToggle: (SuggestedOsirian) -> Void

    var body: some View {
        NavigationStack {
            List(osirians, id: \.userId) { person in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(person.displayName).font(.manrope(.subheadline).bold())
                        Text("\(person.rank) · \(person.title) · \(person.xp) XP").font(.manrope(.caption)).foregroundStyle(OsirisColor.secondary)
                        Text(person.trendingReason).font(.manrope(.caption2)).foregroundStyle(OsirisColor.faint)
                    }
                    Spacer()
                    Button(person.following ? "Following" : "Follow") {
                        onFollowToggle(person)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .navigationTitle("Trending Osirians")
        }
    }
}

private struct PostComposerSheetView: View {
    let plan: WorkoutPlan
    let streakWeeks: Int32
    let onPublish: (PostCreateDraft) -> Void
    @State private var kind = "workout"
    @State private var caption = ""

    var body: some View {
        NavigationStack {
            Form {
                Picker("Activity Type", selection: $kind) {
                    Text("Camera Workout").tag("workout")
                    Text("Claimed Domain").tag("domain_claim")
                    Text("Streak").tag("streak")
                    Text("Mana Crystals").tag("crystal_earn")
                    Text("GPS Run").tag("run")
                }
                TextField("Caption", text: $caption)
                Button("Publish to People's Posts") {
                    let draft = PostCreateDraft(
                        kind: kind,
                        caption: caption.isEmpty ? "Completed \(plan.measureLabel) on Osiris!" : caption,
                        mediaUrl: nil,
                        exerciseKey: plan.option.isCameraExercise ? plan.optionKey : "pushup",
                        sets: plan.sets,
                        repsPerSet: plan.repsPerSet,
                        totalReps: plan.repsPerSet * plan.sets,
                        holdS: plan.option.isHold ? Double(plan.holdSecondsPerSet * plan.sets) : 0.0,
                        distanceM: plan.targetDistanceKm * 1000.0,
                        durationS: 0.0,
                        domainAreaSqkm: kind == "domain_claim" ? 0.45 : 0.0,
                        streakDays: kind == "streak" ? max(streakWeeks, 1) * 7 : 0,
                        crystalsEarned: kind == "crystal_earn" ? 25 : 0,
                        xpEarned: 30,
                        relatedRunId: nil,
                        relatedExerciseSessionId: nil,
                        relatedDomainId: nil,
                        visibility: "public"
                    )
                    onPublish(draft)
                }
                .buttonStyle(.key)
            }
            .navigationTitle("Post Activity")
        }
    }
}

private struct CommentsSheetView: View {
    let comments: [PostCommentItem]
    let onAddComment: (String) -> Void
    @State private var text = ""

    var body: some View {
        NavigationStack {
            VStack {
                List(comments, id: \.id) { c in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(c.authorName) (\(c.authorRank))").font(.manrope(.caption).bold()).foregroundStyle(OsirisColor.secondary)
                        Text(c.body).font(.manrope(.body))
                    }
                }
                HStack {
                    TextField("Add a comment…", text: $text)
                        .textFieldStyle(.roundedBorder)
                    Button("Send") {
                        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !trimmed.isEmpty {
                            onAddComment(trimmed)
                            text = ""
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Comments")
        }
    }
}
