import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import 'pose_frame.dart';

/// Landmark recording for device QA (backlog Phase 5: labeled data under governance).
///
/// Debug builds, and profile builds built with `--dart-define=OSIRIS_POSE_RECORDING=true`, can
/// save the pose stream of a set with the tester's own count of the reps that should count.
/// Release builds can never record. Only joint positions and their confidence are saved, never
/// images; files stay on the phone until the tester copies them off (see
/// `test/exercise/recordings/README.md`), and the replay test turns each one into a regression
/// case for the rep engine.
const bool kPoseRecordingAllowed =
    kDebugMode || (kProfileMode && bool.fromEnvironment('OSIRIS_POSE_RECORDING'));

class PoseRecording {
  static const format = 'osiris-pose-v1';

  final String exerciseKey;
  final String rulesVersion;
  final DateTime recordedAt;
  final String source; // device | synthetic
  final int? labelReps; // reps that should count, as judged by the tester
  final double? labelHoldS; // seconds of good hold, for plank
  final String? note;
  final List<PoseFrame> frames;

  const PoseRecording({
    required this.exerciseKey,
    required this.rulesVersion,
    required this.recordedAt,
    required this.source,
    required this.frames,
    this.labelReps,
    this.labelHoldS,
    this.note,
  });

  static double _r(double v, int digits) => double.parse(v.toStringAsFixed(digits));

  Map<String, dynamic> toJson() => {
        'format': format,
        'exercise_key': exerciseKey,
        'rules_version': rulesVersion,
        'recorded_at': recordedAt.toUtc().toIso8601String(),
        'source': source,
        'label_reps': labelReps,
        'label_hold_s': labelHoldS,
        'note': note,
        'frames': [
          for (final f in frames)
            {
              't': f.tMs,
              'l': {
                for (final e in f.landmarks.entries) e.key: [_r(e.value.x, 1), _r(e.value.y, 1), _r(e.value.likelihood, 2)],
              },
            },
        ],
      };

  factory PoseRecording.fromJson(Map<String, dynamic> j) {
    if (j['format'] != format) throw FormatException('Unsupported pose recording format: ${j['format']}');
    return PoseRecording(
      exerciseKey: j['exercise_key'] as String,
      rulesVersion: j['rules_version'] as String,
      recordedAt: DateTime.parse(j['recorded_at'] as String),
      source: j['source'] as String,
      labelReps: j['label_reps'] as int?,
      labelHoldS: (j['label_hold_s'] as num?)?.toDouble(),
      note: j['note'] as String?,
      frames: [
        for (final f in j['frames'] as List)
          PoseFrame((f as Map)['t'] as int, {
            for (final e in (f['l'] as Map).entries)
              e.key as String: Landmark(
                ((e.value as List)[0] as num).toDouble(),
                ((e.value as List)[1] as num).toDouble(),
                ((e.value as List)[2] as num).toDouble(),
              ),
          }),
      ],
    );
  }
}

/// Collects a set's frames while recording is on. Capped at ten minutes of 30 fps tracking.
class PoseRecorder {
  static const maxFrames = 30 * 60 * 10;

  final List<PoseFrame> frames = [];

  bool get full => frames.length >= maxFrames;

  void add(PoseFrame f) {
    if (!full) frames.add(f);
  }

  PoseRecording finish({
    required String exerciseKey,
    required String rulesVersion,
    int? labelReps,
    double? labelHoldS,
    String? note,
  }) =>
      PoseRecording(
        exerciseKey: exerciseKey,
        rulesVersion: rulesVersion,
        recordedAt: DateTime.now().toUtc(),
        source: 'device',
        frames: List.unmodifiable(frames),
        labelReps: labelReps,
        labelHoldS: labelHoldS,
        note: note,
      );
}

/// Writes [r] as `<dir>/<exercise>_<UTC timestamp>.json` and returns the file.
Future<File> saveRecording(PoseRecording r, Directory dir) async {
  if (!kPoseRecordingAllowed) throw StateError('Pose recording is not available in release builds');
  await dir.create(recursive: true);
  final stamp = r.recordedAt.toUtc().toIso8601String().replaceAll(RegExp(r'[:.]'), '-');
  final file = File(p.join(dir.path, '${r.exerciseKey}_$stamp.json'));
  return file.writeAsString(jsonEncode(r.toJson()));
}
