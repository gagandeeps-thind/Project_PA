import 'dart:async';

import 'package:flutter/widgets.dart';

import 'pose_frame.dart';

/// Inference timing for the on-device performance read-out.
class PoseStats {
  int processed = 0;
  int dropped = 0;
  int totalInferenceUs = 0;
  int maxInferenceUs = 0;
  int? _firstMs;
  int _lastMs = 0;

  void record(int tMs, int inferenceUs) {
    _firstMs ??= tMs;
    _lastMs = tMs;
    processed++;
    totalInferenceUs += inferenceUs;
    if (inferenceUs > maxInferenceUs) maxInferenceUs = inferenceUs;
  }

  double get avgInferenceMs => processed == 0 ? 0 : totalInferenceUs / processed / 1000;
  double get fps {
    final first = _firstMs;
    if (first == null || _lastMs <= first) return 0;
    return (processed - 1) * 1000 / (_lastMs - first);
  }

  @override
  String toString() => '${fps.toStringAsFixed(1)} fps · '
      '${avgInferenceMs.toStringAsFixed(1)} ms avg / ${(maxInferenceUs / 1000).toStringAsFixed(1)} ms max · '
      '$dropped dropped';
}

/// A live stream of poses with an optional camera preview. The camera screen depends only on
/// this, so tests drive it with scripted frames and the app with ML Kit.
abstract class PoseSource {
  Stream<PoseFrame> get frames;

  /// Size of the image the landmark coordinates refer to (upright), once known.
  Size? get imageSize;

  /// True when the preview is mirrored (front camera), so the overlay mirrors too.
  bool get mirrored;

  final PoseStats stats = PoseStats();

  Future<void> start();
  Future<void> stop();

  /// The camera preview, or null when there is none (tests).
  Widget? buildPreview();
}
