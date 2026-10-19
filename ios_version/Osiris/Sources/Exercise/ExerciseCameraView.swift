import SwiftUI
import OsirisShared

/// One camera set. The exercise comes from the cached catalog (a bundled copy offline), so it
/// loads at once; then the shared ExerciseSessionViewModel counts the frames PoseCamera sends.
struct ExerciseCameraView: View {
    let graph: AppGraph
    let key: String
    @State private var load: ExerciseLoad?

    var body: some View {
        Group {
            if let load, let spec = load.spec, let catalog = load.catalog {
                ExerciseSession(graph: graph, spec: spec, catalog: catalog)
            } else if let error = load?.error {
                Text(error)
                    .foregroundStyle(OsirisColor.error)
                    .multilineTextAlignment(.center)
                    .padding(24)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .navigationTitle("Bodyweight")
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(OsirisColor.background)
        .task(id: key) {
            if load == nil { load = try? await IosSupport.shared.loadExercise(graph: graph, key: key) }
        }
    }
}

/// The skeleton overlay's data, kept apart from the screen state so a new frame redraws the
/// overlay alone.
final class PoseOverlay: ObservableObject {
    @Published var frame: PoseFrame?
    @Published var image: CGSize?
}

private struct ExerciseSession: View {
    @StateObject private var model: Observed<ExerciseSessionViewModel, ExerciseSessionState>
    @StateObject private var camera: PoseCamera
    @StateObject private var overlay = PoseOverlay()
    @EnvironmentObject private var nav: Navigator
    @State private var label = ""
    @State private var leaving = false
    private let minLikelihood: Double

    init(graph: AppGraph, spec: ExerciseSpec, catalog: ExerciseCatalog) {
        _model = StateObject(wrappedValue: Observed(graph.exerciseSession(spec: spec, catalog: catalog)) { $0.state })
        _camera = StateObject(wrappedValue: PoseCamera(front: spec.camera == "front"))
        minLikelihood = catalog.minLikelihood
    }

    private var vm: ExerciseSessionViewModel { model.vm }

    var body: some View {
        let s = model.state
        let counting = s.phase == .counting
        ZStack {
            Color.black.ignoresSafeArea()
            ZStack {
                CameraPreview(session: camera.session)
                SkeletonView(overlay: overlay, mirrored: camera.front, minLikelihood: minLikelihood)
            }
            .aspectRatio(overlay.image.map { $0.width / max($0.height, 1) } ?? 3.0 / 4.0, contentMode: .fit)
            VStack(spacing: 8) {
                hud(s.hud)
                if let warning = s.slowWarning {
                    Text(warning)
                        .font(.footnote)
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(OsirisColor.warning.opacity(0.85), in: RoundedRectangle(cornerRadius: 12))
                }
                Spacer()
                controls(s, counting: counting)
            }
            .padding(16)
        }
        .navigationTitle(s.spec.name)
        .navigationBarTitleDisplayMode(.inline)
        // Mid-set the way out is FINISH, so the reps done so far are kept.
        .navigationBarBackButtonHidden(counting || s.phase == .saving)
        .toolbar {
            if s.recordingAllowed {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { vm.setRecordLandmarks(on: !s.recordLandmarks) } label: {
                        Image(systemName: s.recordLandmarks ? "record.circle.fill" : "record.circle")
                            .foregroundStyle(s.recordLandmarks ? OsirisColor.error : OsirisColor.faint)
                    }
                    .disabled(s.phase != .ready)
                    .accessibilityLabel(s.recordLandmarks ? "QA: stop recording landmarks" : "QA: record landmarks")
                }
            }
        }
        .messages(model)
        .onAppear {
            camera.start(
                onStarted: { vm.onCameraStarted() },
                onFrame: { frame, size in
                    overlay.frame = frame
                    if overlay.image != size { overlay.image = size }
                    vm.onFrame(frame: frame)
                },
                onFailed: { vm.onCameraFailed(error: $0) }
            )
        }
        .onDisappear { camera.stop() }
        .textInputAlert(
            "QA: label this recording",
            isPresented: Binding(get: { model.state.askLabel }, set: { _ in }),
            label: s.labelPrompt,
            text: $label,
            confirm: "SAVE",
            dismiss: "DISCARD",
            keyboard: .decimalPad,
            onConfirm: { value in
                label = ""
                vm.labelRecording(value: String(value.prefix(6)))
            },
            onDismiss: {
                label = ""
                vm.labelRecording(value: nil)
            }
        )
        .sheet(
            isPresented: Binding(get: { model.state.result != nil && !leaving }, set: { if !$0 { leaving = true } }),
            onDismiss: { nav.back() }
        ) {
            if let r = model.state.result { ResultSheet(result: r) { leaving = true } }
        }
    }

    private func hud(_ h: ExerciseHud) -> some View {
        HStack(spacing: 16) {
            Text(h.count).font(.system(size: 44, weight: .bold)).monospacedDigit()
            VStack(alignment: .leading, spacing: 2) {
                if let notCounted = h.notCounted { Text(notCounted).font(.caption).foregroundStyle(OsirisColor.warning) }
                Text(h.hint)
            }
            Spacer(minLength: 0)
        }
        .foregroundStyle(.white)
        .padding(12)
        .background(.black.opacity(0.54), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func controls(_ s: ExerciseSessionState, counting: Bool) -> some View {
        if let error = s.cameraError {
            Text(error).foregroundStyle(OsirisColor.error).multilineTextAlignment(.center)
            Button(action: openAppSettings) { Text("OPEN SETTINGS").frame(maxWidth: .infinity, minHeight: 36) }
                .buttonStyle(.borderedProminent)
        } else {
            Button {
                if counting {
                    vm.finish(perf: perf())
                } else {
                    camera.stats.reset()
                    vm.start()
                }
            } label: {
                Text(s.buttonLabel).fontWeight(.semibold).frame(maxWidth: .infinity, minHeight: 36)
            }
            .buttonStyle(.borderedProminent)
            .tint(counting ? OsirisColor.error : OsirisColor.primary)
            .disabled(!(s.phase == .ready || counting))
        }
    }

    /// Debug builds only: the pose timing read-out for the result sheet.
    private func perf() -> String? {
        #if DEBUG
        return camera.stats.summary()
        #else
        return nil
        #endif
    }
}

/// The tracked joints and limbs over the preview, so the player sees what is counted.
private struct SkeletonView: View {
    @ObservedObject var overlay: PoseOverlay
    let mirrored: Bool
    let minLikelihood: Double

    private static let bones = [("shoulder", "elbow"), ("elbow", "wrist"), ("shoulder", "hip"), ("hip", "knee"), ("knee", "ankle")]

    var body: some View {
        Canvas { context, size in
            guard let frame = overlay.frame, let image = overlay.image, image.width > 0, image.height > 0 else { return }
            let sx = size.width / image.width
            let sy = size.height / image.height
            func at(_ l: Landmark?) -> CGPoint? {
                guard let l, l.likelihood >= minLikelihood else { return nil }
                let x = mirrored ? image.width - l.x : l.x
                return CGPoint(x: x * sx, y: l.y * sy)
            }
            func line(_ a: CGPoint?, _ b: CGPoint?) {
                guard let a, let b else { return }
                var path = Path()
                path.move(to: a)
                path.addLine(to: b)
                context.stroke(path, with: .color(OsirisColor.secondary), style: StrokeStyle(lineWidth: 4, lineCap: .round))
            }
            for side in ["left", "right"] {
                for (a, b) in Self.bones { line(at(frame.get(side: side, joint: a)), at(frame.get(side: side, joint: b))) }
            }
            line(at(frame.get(side: "left", joint: "shoulder")), at(frame.get(side: "right", joint: "shoulder")))
            line(at(frame.get(side: "left", joint: "hip")), at(frame.get(side: "right", joint: "hip")))
            for l in frame.landmarks.values {
                if let p = at(l) { context.fill(Path(ellipseIn: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10)), with: .color(.white)) }
            }
        }
        .allowsHitTesting(false)
    }
}

private struct ResultSheet: View {
    let result: SetResult
    let onDone: () -> Void

    private var color: Color {
        switch result.verdict {
        case .verified: return OsirisColor.success
        case .review: return OsirisColor.warning
        default: return OsirisColor.error
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(result.title).font(.title2.bold()).foregroundStyle(color)
                Text(result.amount).font(.title3)
                if let notCounted = result.notCounted { Text(notCounted) }
                ForEach(result.reasons, id: \.self) { Text("• \($0)").foregroundStyle(OsirisColor.muted) }
                Text(result.sync).foregroundStyle(OsirisColor.secondary).padding(.top, 4)
                if let perf = result.perf { Text("Pose: \(perf)").font(.caption).foregroundStyle(OsirisColor.faint) }
                Button(action: onDone) { Text("DONE").frame(maxWidth: .infinity) }
                    .buttonStyle(.bordered)
                    .padding(.top, 8)
            }
            .padding(24)
        }
        .background(OsirisColor.surface)
        .presentationDetents([.large])
    }
}
