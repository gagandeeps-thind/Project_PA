import 'dart:math' as math;

/// One body landmark in image pixels with the detector's confidence (0..1).
class Landmark {
  final double x;
  final double y;
  final double likelihood;

  const Landmark(this.x, this.y, this.likelihood);

  double distanceTo(Landmark o) => math.sqrt((x - o.x) * (x - o.x) + (y - o.y) * (y - o.y));
}

/// The landmarks the rep engine reads, named like the catalog joints with a side prefix
/// (`left_knee`). Kept independent of the ML Kit types so the engine runs in plain tests.
const List<String> kJoints = ['nose', 'shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle'];

/// One camera frame's pose. [tMs] is a monotonic timestamp in milliseconds.
class PoseFrame {
  final int tMs;
  final Map<String, Landmark> landmarks;

  const PoseFrame(this.tMs, this.landmarks);

  Landmark? get(String side, String joint) =>
      landmarks[joint == 'nose' ? 'nose' : '${side}_$joint'];
}

/// Angle at [b] between rays b→a and b→c, in degrees (0..180).
double angleDeg(Landmark a, Landmark b, Landmark c) {
  final v1x = a.x - b.x, v1y = a.y - b.y;
  final v2x = c.x - b.x, v2y = c.y - b.y;
  final n = math.sqrt(v1x * v1x + v1y * v1y) * math.sqrt(v2x * v2x + v2y * v2y);
  if (n == 0) return 0;
  final cos = ((v1x * v2x + v1y * v2y) / n).clamp(-1.0, 1.0);
  return math.acos(cos) * 180 / math.pi;
}

/// Tilt of the segment a→b away from the image's horizontal axis, in degrees (0..90).
double tiltFromHorizontalDeg(Landmark a, Landmark b) {
  final dx = (b.x - a.x).abs(), dy = (b.y - a.y).abs();
  if (dx == 0 && dy == 0) return 0;
  return math.atan2(dy, dx) * 180 / math.pi;
}
