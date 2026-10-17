import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../exercise/exercise_catalog.dart';
import '../exercise/frame_rate_meter.dart';
import '../exercise/pose_frame.dart';
import '../exercise/pose_source.dart';
import '../exercise/rep_engine.dart';
import '../providers.dart';
import '../theme.dart';

/// Explains a reason code to the player.
String explainExerciseReason(String code) => switch (code) {
      'too_fast' => 'Some reps were too fast to be controlled',
      'too_slow' => 'A rep took too long',
      'form_break' => 'Form broke on some reps',
      'wrong_position' => 'Body position did not match the exercise',
      'low_visibility' => 'You were partly out of view',
      'tracking_glitch' => 'The camera lost track of you',
      'unsteady_tracking' => 'Tracking was too unsteady to count. Move closer or add light',
      'partial_range' => 'Some reps were not full range',
      'no_valid_reps' => 'No reps counted',
      'low_valid_ratio' => 'Most reps did not count',
      'replay_suspected' => 'Rep timing was machine-perfect',
      'rate_implausible' => 'More reps per minute than is possible',
      'no_entry_transition' => 'Start outside the position, then move into it',
      'static_pose' => 'No natural movement was seen',
      'hold_too_short' => 'The hold was too short',
      _ => code,
    };

/// Live camera set: preview, skeleton overlay, rep counter and coaching hint. Pose
/// estimation and counting run on the phone; only the summary is saved and uploaded.
class ExerciseCameraScreen extends ConsumerStatefulWidget {
  final ExerciseSpec spec;

  const ExerciseCameraScreen({super.key, required this.spec});

  @override
  ConsumerState<ExerciseCameraScreen> createState() => _ExerciseCameraScreenState();
}

class _ExerciseCameraScreenState extends ConsumerState<ExerciseCameraScreen> with WidgetsBindingObserver {
  PoseSource? _source;
  StreamSubscription<PoseFrame>? _sub;
  RepEngine? _engine;
  DateTime? _startedAt;
  String? _cameraError;
  bool _cameraReady = false;
  // Set when the player opens the settings app from the camera error, so returning to Osiris
  // retries the camera. Without a reason to retry, a resume after a denial (the permission
  // dialog itself pauses and resumes the app) would ask for permission again at once.
  bool _retryOnResume = false;
  bool _saving = false;

  final _frame = ValueNotifier<PoseFrame?>(null);
  final _update = ValueNotifier<EngineUpdate?>(null);
  // Pose frame rate, so a phone too slow to count this exercise says so (accuracy evaluation:
  // below min_pose_fps reps are missed, never invented).
  var _meter = FrameRateMeter();
  late final _slowDetector = SlowTrackingDetector(widget.spec.minPoseFps);
  final _slowFps = ValueNotifier<double?>(null);

  bool get _recording => _engine != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _openCamera();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _closeCamera();
    _frame.dispose();
    _update.dispose();
    _slowFps.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The camera must be released in the background and reopened on return. The camera
    // permission prompt also makes the app inactive; a camera still starting is left alone.
    if ((state == AppLifecycleState.inactive || state == AppLifecycleState.paused) && _cameraReady) {
      _closeCamera();
    } else if (state == AppLifecycleState.resumed && _source == null && (_cameraError == null || _retryOnResume)) {
      _retryOnResume = false;
      _openCamera();
    }
  }

  Future<void> _openCamera() async {
    _meter = FrameRateMeter(); // a reopened camera warms up again
    final source = ref.read(poseSourceFactoryProvider)();
    _source = source;
    _sub = source.frames.listen(_onFrame);
    try {
      await source.start();
      _cameraReady = true;
      if (mounted) setState(() => _cameraError = null);
    } on Object catch (e) {
      // Drop the failed camera so returning from the settings app opens a fresh one;
      // keeping it made the resume handler skip the retry and left the error on screen.
      _closeCamera();
      if (mounted) setState(() => _cameraError = _cameraMessage(e));
    }
  }

  String _cameraMessage(Object e) {
    final text = e.toString();
    if (text.contains('Denied') || text.contains('denied')) {
      return 'Camera access is off. Allow it in your phone settings to count reps.';
    }
    return 'The camera could not start.';
  }

  void _closeCamera() {
    _cameraReady = false;
    _sub?.cancel();
    _sub = null;
    final source = _source;
    _source = null;
    if (source != null) unawaited(source.stop().catchError((_) {}));
  }

  void _onFrame(PoseFrame f) {
    _frame.value = f;
    _meter.add(f.tMs);
    final fps = _meter.fps;
    final slow = _slowDetector.update(fps) ? fps : null;
    if ((slow == null) != (_slowFps.value == null) || (slow != null && slow.round() != _slowFps.value!.round())) {
      _slowFps.value = slow;
    }
    final engine = _engine;
    if (engine == null) return;
    final u = engine.addFrame(f);
    final prev = _update.value;
    // Rebuild the HUD only when something the player sees changed, not on every frame.
    if (prev == null ||
        prev.validReps != u.validReps ||
        prev.attemptedReps != u.attemptedReps ||
        prev.hint != u.hint ||
        prev.holdS.floor() != u.holdS.floor()) {
      _update.value = u;
    }
  }

  void _start() {
    final catalog = ref.read(exerciseCatalogProvider).value;
    if (catalog == null) return;
    setState(() {
      _engine = RepEngine(widget.spec, catalog);
      _startedAt = DateTime.now().toUtc();
      _update.value = null;
    });
  }

  Future<void> _finish() async {
    final engine = _engine;
    if (engine == null || _saving) return;
    final summary = engine.finish();
    final stats = _source?.stats.toString();
    setState(() {
      _engine = null;
      _saving = true;
    });
    SetOutcome? outcome;
    try {
      outcome = await ref.read(exerciseRecorderProvider)(summary, _startedAt!);
    } on Object {
      outcome = null;
    }
    if (!mounted) return;
    setState(() => _saving = false);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ResultSheet(spec: widget.spec, summary: summary, outcome: outcome, perf: kDebugMode ? stats : null),
    );
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final spec = widget.spec;
    final ready = ref.watch(exerciseCatalogProvider).hasValue;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(title: Text(spec.name), backgroundColor: Colors.black),
      body: Stack(children: [
        Positioned.fill(child: _cameraLayer()),
        Positioned(
          left: 16,
          right: 16,
          top: 12,
          child: ValueListenableBuilder<EngineUpdate?>(
            valueListenable: _update,
            builder: (_, u, _) => Column(mainAxisSize: MainAxisSize.min, children: [
              _Hud(spec: spec, update: u, recording: _recording),
              ValueListenableBuilder<double?>(
                valueListenable: _slowFps,
                builder: (_, fps, _) => fps == null ? const SizedBox.shrink() : _SlowWarning(spec: spec, fps: fps),
              ),
            ]),
          ),
        ),
        Positioned(
          left: 16,
          right: 16,
          bottom: 24,
          child: _cameraError != null
              ? Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(_cameraError!, textAlign: TextAlign.center, style: const TextStyle(color: OsirisTheme.error)),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: () {
                      _retryOnResume = true;
                      Geolocator.openAppSettings();
                    },
                    style: ElevatedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                    child: const Text('OPEN SETTINGS'),
                  ),
                ])
              : ElevatedButton(
                  key: const Key('exercise-action'),
                  onPressed: _saving || !ready ? null : (_recording ? _finish : _start),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _recording ? OsirisTheme.error : OsirisTheme.primary,
                    minimumSize: const Size.fromHeight(52),
                  ),
                  child: Text(_saving ? 'SAVING…' : (_recording ? 'FINISH' : 'START')),
                ),
        ),
      ]),
    );
  }

  Widget _cameraLayer() {
    final source = _source;
    final preview = source?.buildPreview();
    final size = source?.imageSize;
    final overlay = ValueListenableBuilder<PoseFrame?>(
      valueListenable: _frame,
      builder: (_, f, _) => CustomPaint(
        painter: SkeletonPainter(frame: f, imageSize: source?.imageSize, mirrored: source?.mirrored ?? false),
      ),
    );
    final layers = Stack(fit: StackFit.expand, children: [?preview, overlay]);
    if (size == null || size.height == 0) return layers;
    return Center(child: AspectRatio(aspectRatio: size.width / size.height, child: layers));
  }
}

class _Hud extends StatelessWidget {
  final ExerciseSpec spec;
  final EngineUpdate? update;
  final bool recording;

  const _Hud({required this.spec, required this.update, required this.recording});

  @override
  Widget build(BuildContext context) {
    final u = update;
    final big = spec.isHold ? '${(u?.holdS ?? 0).toStringAsFixed(0)} s' : '${u?.validReps ?? 0}';
    final hint = !recording ? spec.instructions : (u?.hint.isNotEmpty ?? false) ? u!.hint : 'Get into position';
    return DecoratedBox(
      decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(children: [
          Text(big, key: const Key('exercise-count'),
              style: const TextStyle(fontSize: 44, fontWeight: FontWeight.bold, color: Colors.white)),
          const SizedBox(width: 16),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (recording && !spec.isHold && (u?.attemptedReps ?? 0) > (u?.validReps ?? 0))
                Text('${u!.attemptedReps - u.validReps} not counted',
                    style: const TextStyle(color: Colors.amber, fontSize: 12)),
              Text(hint, key: const Key('exercise-hint'), style: const TextStyle(color: Colors.white, fontSize: 15)),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _SlowWarning extends StatelessWidget {
  final ExerciseSpec spec;
  final double fps;

  const _SlowWarning({required this.spec, required this.fps});

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('exercise-slow-warning'),
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: Colors.amber.shade900.withValues(alpha: 0.9), borderRadius: BorderRadius.circular(12)),
      child: Text(
        'This phone is tracking ${fps.round()} frames a second; ${spec.name.toLowerCase()} needs '
        '${spec.minPoseFps.round()}. Some reps may not count. More light or closing other apps can help.',
        style: const TextStyle(color: Colors.white, fontSize: 13),
      ),
    );
  }
}

class _ResultSheet extends StatelessWidget {
  final ExerciseSpec spec;
  final SessionSummary summary;
  final SetOutcome? outcome;
  final String? perf;

  const _ResultSheet({required this.spec, required this.summary, required this.outcome, this.perf});

  @override
  Widget build(BuildContext context) {
    final (title, color) = switch (summary.verdict) {
      'verified' => ('Verified', OsirisTheme.success),
      'review' => ('Sent for review', Colors.amber),
      _ => ('Not verified', OsirisTheme.error),
    };
    final amount = spec.isHold ? '${summary.holdS.toStringAsFixed(0)} s hold' : '${summary.repsValid} reps';
    final o = outcome;
    final sync = o == null
        ? 'This set could not be saved on your phone.'
        : o.uploaded
            ? (o.xpAwarded > 0 ? '+${o.xpAwarded} XP' : 'Uploaded. No XP for this set.')
            : 'Saved on your phone. It will upload when you are online.';
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, key: const Key('exercise-verdict'), style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('${spec.name}: $amount', key: const Key('exercise-amount'), style: const TextStyle(fontSize: 18)),
          if (!spec.isHold && summary.repsAttempted > summary.repsValid)
            Text('${summary.repsAttempted - summary.repsValid} reps did not count'),
          const SizedBox(height: 8),
          for (final r in summary.reasons) Text('• ${explainExerciseReason(r)}', style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 12),
          Text(sync, style: const TextStyle(color: OsirisTheme.secondary)),
          if (perf != null) ...[
            const SizedBox(height: 8),
            Text('Pose: $perf', style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(onPressed: () => Navigator.of(context).pop(), child: const Text('DONE')),
          ),
        ]),
      ),
    );
  }
}

/// Draws the tracked joints and limbs over the preview so the player sees what is counted.
class SkeletonPainter extends CustomPainter {
  final PoseFrame? frame;
  final Size? imageSize;
  final bool mirrored;
  final double minLikelihood;

  SkeletonPainter({required this.frame, required this.imageSize, required this.mirrored, this.minLikelihood = 0.5});

  static const _bones = [
    ('shoulder', 'elbow'),
    ('elbow', 'wrist'),
    ('shoulder', 'hip'),
    ('hip', 'knee'),
    ('knee', 'ankle'),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final f = frame, img = imageSize;
    if (f == null || img == null || img.width == 0 || img.height == 0) return;
    final sx = size.width / img.width, sy = size.height / img.height;
    Offset? at(Landmark? l) {
      if (l == null || l.likelihood < minLikelihood) return null;
      final x = mirrored ? img.width - l.x : l.x;
      return Offset(x * sx, l.y * sy);
    }

    final bone = Paint()
      ..color = OsirisTheme.secondary
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    final joint = Paint()..color = Colors.white;
    for (final side in ['left', 'right']) {
      for (final (a, b) in _bones) {
        final p1 = at(f.get(side, a)), p2 = at(f.get(side, b));
        if (p1 != null && p2 != null) canvas.drawLine(p1, p2, bone);
      }
    }
    final ls = at(f.get('left', 'shoulder')), rs = at(f.get('right', 'shoulder'));
    final lh = at(f.get('left', 'hip')), rh = at(f.get('right', 'hip'));
    if (ls != null && rs != null) canvas.drawLine(ls, rs, bone);
    if (lh != null && rh != null) canvas.drawLine(lh, rh, bone);
    for (final l in f.landmarks.values) {
      final p = at(l);
      if (p != null) canvas.drawCircle(p, 5, joint);
    }
  }

  @override
  bool shouldRepaint(SkeletonPainter old) => old.frame != frame || old.imageSize != imageSize;
}
