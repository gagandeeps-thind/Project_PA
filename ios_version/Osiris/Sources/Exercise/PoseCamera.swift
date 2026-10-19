import AVFoundation
import SwiftUI
import Vision
import OsirisShared

/// Camera plus Apple Vision body pose, the iOS counterpart of the Android PoseCamera and
/// PoseAnalyzer. Frames arrive upright (portrait) and unmirrored, so landmark pixels match the
/// image the engine expects on Android; the overlay mirrors them for the front camera.
///
/// At most one frame is in flight: Vision runs synchronously on the capture queue and the
/// output discards late frames, so a slow phone drops frames instead of queueing them. Each
/// frame is handed to the main thread, one at a time, in order.
final class PoseCamera: NSObject, ObservableObject {
    let session = AVCaptureSession()
    let front: Bool
    let stats = PoseStats()

    private let queue = DispatchQueue(label: "com.osiris.player.pose")
    private let output = AVCaptureVideoDataOutput()
    private let request = VNDetectHumanBodyPoseRequest()
    private var configured = false
    private var onFrame: ((PoseFrame, CGSize) -> Void)?
    private var onFailed: ((AppError) -> Void)?
    private var runtimeError: NSObjectProtocol?

    /// Vision joints by the names the shared rep engine reads (`PoseFrame.JOINTS`, with sides).
    private static let joints: [(VNHumanBodyPoseObservation.JointName, String)] = [
        (.nose, "nose"),
        (.leftShoulder, "left_shoulder"), (.rightShoulder, "right_shoulder"),
        (.leftElbow, "left_elbow"), (.rightElbow, "right_elbow"),
        (.leftWrist, "left_wrist"), (.rightWrist, "right_wrist"),
        (.leftHip, "left_hip"), (.rightHip, "right_hip"),
        (.leftKnee, "left_knee"), (.rightKnee, "right_knee"),
        (.leftAnkle, "left_ankle"), (.rightAnkle, "right_ankle"),
    ]

    init(front: Bool) {
        self.front = front
        super.init()
    }

    /// Asks for camera access when needed, then starts the camera. Callbacks run on the main thread.
    func start(
        onStarted: @escaping () -> Void,
        onFrame: @escaping (PoseFrame, CGSize) -> Void,
        onFailed: @escaping (AppError) -> Void
    ) {
        self.onFrame = onFrame
        self.onFailed = onFailed
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            run(onStarted)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    if granted { self.run(onStarted) } else { onFailed(IosSupport.shared.cameraOff()) }
                }
            }
        default:
            onFailed(IosSupport.shared.cameraOff())
        }
    }

    func stop() {
        onFrame = nil
        onFailed = nil
        if let runtimeError { NotificationCenter.default.removeObserver(runtimeError) }
        runtimeError = nil
        queue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
    }

    private func run(_ onStarted: @escaping () -> Void) {
        runtimeError = NotificationCenter.default.addObserver(
            forName: .AVCaptureSessionRuntimeError, object: session, queue: .main
        ) { [weak self] _ in self?.onFailed?(IosSupport.shared.cameraUnavailable()) }
        queue.async { [weak self] in
            guard let self else { return }
            guard self.configured || self.configure() else {
                DispatchQueue.main.async { self.onFailed?(IosSupport.shared.cameraUnavailable()) }
                return
            }
            self.session.startRunning()
            DispatchQueue.main.async { onStarted() }
        }
    }

    /// On the capture queue: VGA is plenty for body pose and keeps Vision fast.
    private func configure() -> Bool {
        let position: AVCaptureDevice.Position = front ? .front : .back
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position),
              let input = try? AVCaptureDeviceInput(device: device) else { return false }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        if session.canSetSessionPreset(.vga640x480) { session.sessionPreset = .vga640x480 }
        guard session.canAddInput(input), session.canAddOutput(output) else { return false }
        session.addInput(input)
        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.setSampleBufferDelegate(self, queue: queue)
        session.addOutput(output)
        if let connection = output.connection(with: .video) {
            if connection.isVideoOrientationSupported { connection.videoOrientation = .portrait }
            if connection.isVideoMirroringSupported {
                connection.automaticallyAdjustsVideoMirroring = false
                connection.isVideoMirrored = false
            }
        }
        configured = true
        return true
    }
}

extension PoseCamera: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixels = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let width = Double(CVPixelBufferGetWidth(pixels))
        let height = Double(CVPixelBufferGetHeight(pixels))
        // The capture clock is monotonic and shared by every session, so a reopened camera
        // continues the timeline.
        let tMs = Int64((CMSampleBufferGetPresentationTimeStamp(sampleBuffer).seconds * 1000).rounded())
        let started = DispatchTime.now().uptimeNanoseconds
        let handler = VNImageRequestHandler(cvPixelBuffer: pixels, orientation: .up, options: [:])
        do {
            try handler.perform([request])
        } catch {
            stats.fail()
            return
        }
        stats.record(tMs: tMs, latencyUs: Int64((DispatchTime.now().uptimeNanoseconds - started) / 1_000))

        var landmarks: [String: Landmark] = [:]
        if let pose = request.results?.first, let points = try? pose.recognizedPoints(.all) {
            for (joint, name) in Self.joints {
                guard let p = points[joint], p.confidence > 0 else { continue }
                // Vision is normalised with the origin bottom-left; the engine uses top-left pixels.
                landmarks[name] = Landmark(x: Double(p.location.x) * width, y: (1 - Double(p.location.y)) * height, likelihood: Double(p.confidence))
            }
        }
        let frame = PoseFrame(tMs: tMs, landmarks: landmarks)
        let size = CGSize(width: width, height: height)
        DispatchQueue.main.async { [weak self] in self?.onFrame?(frame, size) }
    }
}

/// Pose timing for the debug read-out on the result sheet: rate, mean and p95 latency.
final class PoseStats {
    private let lock = NSLock()
    private var latenciesUs: [Int64] = []
    private var firstMs: Int64 = 0
    private var lastMs: Int64 = 0
    private var failed = 0
    private static let maxSamples = 30 * 60 * 10

    func record(tMs: Int64, latencyUs: Int64) {
        lock.lock()
        defer { lock.unlock() }
        if latenciesUs.isEmpty { firstMs = tMs }
        lastMs = tMs
        if latenciesUs.count < Self.maxSamples { latenciesUs.append(latencyUs) }
    }

    func fail() {
        lock.lock()
        defer { lock.unlock() }
        failed += 1
    }

    func summary() -> String? {
        lock.lock()
        defer { lock.unlock() }
        let n = latenciesUs.count
        guard n >= 2 else { return nil }
        let sorted = latenciesUs.sorted()
        let meanMs = Double(sorted.reduce(0, +)) / Double(n) / 1000
        let p95Ms = Double(sorted[Int(Double(n - 1) * 0.95)]) / 1000
        let fps = Double(n - 1) * 1000 / Double(max(lastMs - firstMs, 1))
        return String(format: "%d frames, %.1f fps, %.0f ms mean, %.0f ms p95, %d failed", n, fps, meanMs, p95Ms, failed)
    }

    func reset() {
        lock.lock()
        defer { lock.unlock() }
        latenciesUs.removeAll()
        failed = 0
    }
}

/// The live camera image, scaled to fit like the pose overlay above it.
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspect
        return view
    }

    func updateUIView(_ view: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }
}
