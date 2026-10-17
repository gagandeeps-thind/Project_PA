import 'dart:collection';

/// Pose frames per second over a sliding window of the most recent frame times.
///
/// The window also skips model warm-up: ML Kit's first frame can take seconds (report 14), and
/// that gap leaves the window after [window] frames.
class FrameRateMeter {
  final int window;
  final _times = ListQueue<int>();

  FrameRateMeter({this.window = 15});

  void add(int tMs) {
    _times.addLast(tMs);
    while (_times.length > window) {
      _times.removeFirst();
    }
  }

  /// Null until the window is full.
  double? get fps {
    if (_times.length < window) return null;
    final span = _times.last - _times.first;
    return span <= 0 ? null : (_times.length - 1) * 1000 / span;
  }
}

/// Whether pose tracking is too slow for an exercise, with hysteresis so the warning does not
/// flicker when the rate hovers at the limit: on below [minFps], off again at 20% above it.
class SlowTrackingDetector {
  final double minFps;
  bool _slow = false;

  SlowTrackingDetector(this.minFps);

  bool update(double? fps) {
    if (fps == null) return _slow;
    if (!_slow && fps < minFps) _slow = true;
    if (_slow && fps >= minFps * 1.2) _slow = false;
    return _slow;
  }
}
