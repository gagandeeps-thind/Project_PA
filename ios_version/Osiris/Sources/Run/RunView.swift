import SwiftUI
import OsirisShared

/// Run recording: live route, challenge course overlay, nearby challenges and the finish flow,
/// all driven by the shared RunViewModel. GPS runs while this screen is open, recording or not.
struct RunView: View {
    @StateObject private var model: Observed<RunViewModel, RunState>
    @StateObject private var location = LocationTracker()
    @EnvironmentObject private var nav: Navigator
    @State private var courseName = ""
    @State private var shareText: SharedText?

    init(graph: AppGraph, challengeId: Int32?) {
        let id = challengeId.map { KotlinInt(int: $0) }
        _model = StateObject(wrappedValue: Observed(graph.run(challengeId: id)) { $0.state })
    }

    var body: some View {
        let s = model.state
        ZStack(alignment: .top) {
            if s.locating && s.position == nil {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                RunMap(
                    position: s.position,
                    course: s.course,
                    trace: s.trace,
                    nearby: s.challengeId == nil ? s.nearby : [],
                    follow: s.recording,
                    onChallenge: s.recording ? nil : { nav.open(.challenge($0)) }
                )
                .ignoresSafeArea(edges: .bottom)
            }
            VStack(spacing: 8) {
                if s.challengeId != nil && !s.recording {
                    Text("Go to the green start zone, then tap START. Finish inside the red zone. "
                         + "Run safely: obey traffic rules and stop if you feel unwell.")
                        .padding(12)
                        .background(OsirisColor.surface, in: RoundedRectangle(cornerRadius: 12))
                }
                if s.recording, let run = s.run { metrics(s, run) }
            }
            .padding(12)
        }
        .overlay(alignment: .bottomTrailing) { runButton(s).padding(16) }
        .background(OsirisColor.background)
        .navigationTitle(s.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if s.recording {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { model.vm.requestDiscard() } label: { Image(systemName: "trash") }
                        .disabled(s.busy)
                        .accessibilityLabel("Discard run")
                }
            }
        }
        .messages(model)
        .onAppear {
            location.start(
                onFix: { model.vm.onLocation(fix: $0) },
                onUnavailable: { model.vm.onLocationUnavailable(error: $0) }
            )
            location.setRecording(s.recording)
        }
        .onDisappear { location.stop() }
        .onChange(of: s.recording) { location.setRecording($0) }
        .modifier(RunDialogs(model: model, courseName: $courseName, shareText: $shareText))
    }

    private func metrics(_ s: RunState, _ run: ActiveRun) -> some View {
        HStack {
            metric("TIME", s.elapsed)
            metric("DISTANCE", s.distance)
            metric("PACE /km", s.pace.map { $0.replacingOccurrences(of: " /km", with: "") } ?? "--")
            metric(s.offline ? "OFFLINE" : "SYNCED", "\(run.uploaded)/\(run.nextSequence)", color: s.offline ? OsirisColor.warning : nil)
        }
        .padding(12)
        .background(OsirisColor.surface.opacity(0.92), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }

    private func metric(_ label: String, _ value: String, color: Color? = nil) -> some View {
        VStack {
            Text(value).font(.headline.monospacedDigit()).foregroundStyle(color ?? .white)
            Text(label).font(.caption2).foregroundStyle(color ?? OsirisColor.faint)
        }
        .frame(maxWidth: .infinity)
    }

    private func runButton(_ s: RunState) -> some View {
        // A run cannot start before the first GPS fix.
        let waiting = s.busy || (!s.recording && s.position == nil)
        let label = s.recording ? "FINISH RUN" : (s.position == nil ? "LOCATING…" : "START RUN")
        let color = s.recording ? OsirisColor.error : (s.position == nil ? OsirisColor.surface : OsirisColor.primary)
        return Button { if !waiting { model.vm.toggle() } } label: {
            HStack(spacing: 8) {
                if waiting { ProgressView().tint(.white) } else { Image(systemName: s.recording ? "stop.fill" : "play.fill") }
                Text(label).fontWeight(.semibold)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .foregroundStyle(.white)
            .background(color, in: Capsule())
        }
        .accessibilityLabel(label)
    }
}

/// Every dialog the run flow asks for, with the Flutter copy. Each closes through the view model.
private struct RunDialogs: ViewModifier {
    @ObservedObject var model: Observed<RunViewModel, RunState>
    @Binding var courseName: String
    @Binding var shareText: SharedText?

    private var vm: RunViewModel { model.vm }
    private var dialog: RunDialog? { model.state.dialog }

    /// Presented while the dialog is of type [T]. A dismissal by swipe or button closes it in the
    /// view model, unless a button already moved the flow on to another dialog.
    private func showing<T>(_ type: T.Type) -> Binding<Bool> {
        Binding(
            get: { dialog is T },
            set: { shown in
                if !shown, (vm.state.value as? RunState)?.dialog is T { vm.dismissDialog() }
            }
        )
    }

    func body(content: Content) -> some View {
        content
            .alert("Unfinished run found", isPresented: showing(RunDialogStaleRun.self)) {
                Button("SUBMIT IT") { vm.finish() }
                Button("DISCARD", role: .destructive) { vm.discard() }
            } message: {
                Text("A run you started a while ago was never finished. Submit what was recorded, or discard it and start fresh?")
            }
            .alert("It's dark out", isPresented: showing(RunDialogLowLight.self)) {
                Button("START ANYWAY") { vm.start(confirmedLowLight: true) }
                Button("NOT NOW", role: .cancel) { vm.dismissDialog() }
            } message: {
                Text("Run on lit routes you know, wear something bright or reflective, "
                     + "and tell someone your route and when you expect to be back.")
            }
            .alert("Discard this run?", isPresented: showing(RunDialogConfirmDiscard.self)) {
                Button("DISCARD", role: .destructive) { vm.discard() }
                Button("KEEP RUNNING", role: .cancel) { vm.dismissDialog() }
            } message: {
                Text("The recorded route is deleted from this phone and the run will not count.")
            }
            .alert((dialog as? RunDialogInfo)?.title ?? "", isPresented: showing(RunDialogInfo.self)) {
                Button("OK") { vm.dismissDialog() }
            } message: {
                Text((dialog as? RunDialogInfo)?.body ?? "")
            }
            .textInputAlert(
                "Make it a challenge?",
                isPresented: showing(RunDialogOfferCourse.self),
                message: "Register this route as a course others can challenge? The first and last 150 m are trimmed off for your privacy.",
                label: "Course name",
                text: $courseName,
                confirm: "REGISTER",
                dismiss: "NOT NOW",
                onConfirm: { name in
                    if let offer = dialog as? RunDialogOfferCourse { vm.registerCourse(runId: offer.runId, name: name) }
                    courseName = ""
                },
                onDismiss: { vm.dismissDialog() }
            )
            // A sheet rather than an alert, so SHARE does not close the celebration.
            .sheet(isPresented: showing(RunDialogCelebrate.self)) {
                if let d = dialog as? RunDialogCelebrate { celebrate(d) }
            }
    }

    private func celebrate(_ d: RunDialogCelebrate) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(d.title, systemImage: "trophy.fill").font(.title2.bold()).foregroundStyle(OsirisColor.gold)
            Text(d.summary)
            Text(d.xp).foregroundStyle(OsirisColor.secondary)
            if let week = d.week { Text(week).padding(.top, 4) }
            if let tomorrow = d.tomorrow { Text(tomorrow).foregroundStyle(OsirisColor.muted) }
            HStack {
                Button {
                    Task { @MainActor in
                        if let text = try? await vm.shareRun(runId: d.runId) { shareText = SharedText(text: text) }
                    }
                } label: { Label("SHARE", systemImage: "square.and.arrow.up") }
                Spacer()
                Button("NICE") { vm.dismissDialog() }.buttonStyle(.borderedProminent)
            }
            .padding(.top, 12)
        }
        .padding(24)
        .presentationDetents([.medium])
        .sheet(item: $shareText) { ShareSheet(text: $0.text) }
    }
}
