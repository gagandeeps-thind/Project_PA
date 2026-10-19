import SwiftUI
import OsirisShared

/// The player's registered courses, and publishing a challenge on one.
struct CoursesView: View {
    @StateObject private var model: Observed<CoursesViewModel, CoursesState>
    @EnvironmentObject private var nav: Navigator
    @State private var publishing: CourseSummary?

    init(graph: AppGraph) {
        _model = StateObject(wrappedValue: Observed(graph.courses()) { $0.state })
    }

    var body: some View {
        let s = model.state
        LoadableContent(state: s.courses, onRetry: { model.vm.refresh() }) { (courses: [CourseSummary]) in
            List {
                if courses.isEmpty {
                    EmptyState(
                        icon: "point.topleft.down.curvedto.point.bottomright.up",
                        title: "No courses yet.",
                        detail: "Finish a verified run of at least ~0.7 km and register it as a course."
                    )
                    .listRowBackground(Color.clear)
                }
                ForEach(courses, id: \.id) { c in tile(c) }
            }
            .refreshable { model.vm.refresh() }
        }
        .background(OsirisColor.background)
        .navigationTitle("MY COURSES")
        .navigationBarTitleDisplayMode(.inline)
        .messages(model)
        .sheet(item: Binding(get: { publishing.map(PublishTarget.init) }, set: { if $0 == nil { publishing = nil } })) { target in
            PublishSheet(course: target.course, model: model, busy: s.publishing) { publishing = nil }
        }
        .onChange(of: s.openChallengeId?.int32Value) { id in
            guard let id else { return }
            publishing = nil
            model.vm.opened()
            nav.open(.challenge(id))
        }
    }

    private func tile(_ c: CourseSummary) -> some View {
        HStack {
            Image(systemName: c.isLoop ? "arrow.triangle.2.circlepath" : "point.topleft.down.curvedto.point.bottomright.up")
                .foregroundStyle(OsirisColor.secondary)
            VStack(alignment: .leading) {
                Text(c.name).fontWeight(.bold)
                Text("\(Format.shared.distance(metres: c.distanceM)) • your time \(Format.shared.duration(seconds: c.benchmarkSeconds))")
                    .font(.subheadline).foregroundStyle(OsirisColor.muted)
            }
            Spacer()
            if c.status != "active" {
                Text(c.status.uppercased()).foregroundStyle(OsirisColor.error)
            } else if let live = c.openChallengeId?.int32Value {
                Button("VIEW LIVE") { nav.open(.challenge(live)) }.buttonStyle(.borderless)
            } else {
                Button("PUBLISH") { publishing = c }.buttonStyle(.borderedProminent)
            }
        }
    }
}

/// `.sheet(item:)` needs an identifiable value.
private struct PublishTarget: Identifiable {
    let course: CourseSummary
    var id: Int32 { course.id }
}

/// Publishing a challenge. The sheet stays open until the challenge is published (the screen then
/// opens it), so a retry after a failure reuses the same draft and idempotency key.
private struct PublishSheet: View {
    let course: CourseSummary
    @ObservedObject var model: Observed<CoursesViewModel, CoursesState>
    let busy: Bool
    let onClose: () -> Void

    @State private var title: String
    @State private var window: Int32 = 72
    @State private var safety = ""
    @State private var error: String?
    @State private var draft: ChallengeDraft?

    private static let windows: [(hours: Int32, label: String)] = [(24, "1 day"), (72, "3 days"), (168, "1 week"), (336, "2 weeks")]

    init(course: CourseSummary, model: Observed<CoursesViewModel, CoursesState>, busy: Bool, onClose: @escaping () -> Void) {
        self.course = course
        self.model = model
        self.busy = busy
        self.onClose = onClose
        _title = State(initialValue: "Beat my \(course.name)")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Challengers must beat your time of \(Format.shared.duration(seconds: course.benchmarkSeconds)) "
                         + "over \(Format.shared.distance(metres: course.distanceM)). Terms cannot be edited after publishing.")
                }
                Section {
                    TextField("Title", text: $title)
                        .onChange(of: title) { if $0.count > 80 { title = String($0.prefix(80)) } }
                    if let error { Text(error).font(.caption).foregroundStyle(OsirisColor.error) }
                    Picker("Open for", selection: $window) {
                        ForEach(Self.windows, id: \.hours) { Text($0.label).tag($0.hours) }
                    }
                    TextField("Safety notes (optional)", text: $safety, prompt: Text("e.g. busy crossing at the halfway point"), axis: .vertical)
                        .onChange(of: safety) { if $0.count > 200 { safety = String($0.prefix(200)) } }
                } footer: {
                    Text("Entry is free. Rewards are XP and badges.")
                }
            }
            .navigationTitle("Publish challenge")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("CANCEL", action: onClose) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "PUBLISHING…" : "PUBLISH", action: publish).disabled(busy)
                }
            }
            .messages(model)
        }
        .interactiveDismissDisabled(busy)
    }

    private func publish() {
        let trimmedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedNotes = safety.trimmingCharacters(in: .whitespacesAndNewlines)
        let notes: String? = trimmedNotes.isEmpty ? nil : trimmedNotes
        // Reuse the draft while its terms are unchanged, so a retried tap keeps its idempotency key.
        let d: ChallengeDraft
        if let existing = draft, existing.title == trimmedTitle, existing.windowHours == window, existing.safetyNotes == notes {
            d = existing
        } else {
            d = model.vm.draft(course: course, title: trimmedTitle, windowHours: window, safetyNotes: notes)
        }
        draft = d
        error = d.validate()
        if error == nil { model.vm.publish(draft: d) }
    }
}
