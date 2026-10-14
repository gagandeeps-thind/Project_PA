import 'dart:io';
import 'dart:math' as math;

import 'package:osiris_customer/exercise/exercise_catalog.dart';
import 'package:osiris_customer/exercise/pose_frame.dart';

/// Builds synthetic BlazePose-like skeletons from joint angles, so engine tests can replay
/// genuine and fake movement without a camera.

ExerciseCatalog loadCatalog() => ExerciseCatalog.parse(File('assets/exercise_catalog.json').readAsStringSync());

const double _scale = 400;

class Noise {
  final math.Random _r;
  final double px;
  Noise(int seed, {this.px = 1.5}) : _r = math.Random(seed);
  double next() => px == 0 ? 0 : (_r.nextDouble() + _r.nextDouble() - 1) * px;
}

(double, double) _step(double x, double y, double deg, double len) =>
    (x + math.cos(deg * math.pi / 180) * len * _scale, y + math.sin(deg * math.pi / 180) * len * _scale);

/// Side-view skeleton anchored at the hip. [torsoDeg] is the direction hip → shoulder in image
/// degrees (−90 is straight up, 180 is to the left); every other value is the interior angle
/// at that joint. Pass [thighDeg] instead to fix the thigh and derive the torso (sit-ups).
Map<String, Landmark> sideChain(
  String side, {
  double torsoDeg = -90,
  double? thighDeg,
  double hip = 180,
  double knee = 180,
  double shoulder = 20,
  double elbow = 170,
  double ox = 200,
  double oy = 250,
  double likelihood = 0.95,
  Noise? noise,
}) {
  final torso = thighDeg == null ? torsoDeg : thighDeg - hip;
  final thigh = torso + hip;
  final shank = thigh + 180 - knee;
  final upperArm = torso + 180 + shoulder;
  final forearm = upperArm + 180 - elbow;
  final pts = <String, (double, double)>{'hip': (ox, oy)};
  pts['shoulder'] = _step(ox, oy, torso, 0.30);
  pts['knee'] = _step(ox, oy, thigh, 0.25);
  pts['ankle'] = _step(pts['knee']!.$1, pts['knee']!.$2, shank, 0.25);
  pts['elbow'] = _step(pts['shoulder']!.$1, pts['shoulder']!.$2, upperArm, 0.17);
  pts['wrist'] = _step(pts['elbow']!.$1, pts['elbow']!.$2, forearm, 0.15);
  final s = pts['shoulder']!;
  final nose = _step(s.$1, s.$2, torso, 0.08);
  final out = <String, Landmark>{
    for (final e in pts.entries)
      '${side}_${e.key}': Landmark(e.value.$1 + (noise?.next() ?? 0), e.value.$2 + (noise?.next() ?? 0), likelihood),
  };
  out['nose'] = Landmark(nose.$1, nose.$2, likelihood);
  return out;
}

/// Both sides of a side-on body; the far side is slightly offset and less confident.
Map<String, Landmark> sideBody({
  double torsoDeg = -90,
  double? thighDeg,
  double hip = 180,
  double knee = 180,
  double shoulder = 20,
  double elbow = 170,
  double? farKnee,
  double? farHip,
  double nearLikelihood = 0.95,
  double farLikelihood = 0.7,
  Noise? noise,
}) =>
    {
      ...sideChain('right', torsoDeg: torsoDeg, thighDeg: thighDeg, hip: farHip ?? hip, knee: farKnee ?? knee,
          shoulder: shoulder, elbow: elbow, ox: 204, likelihood: farLikelihood, noise: noise),
      ...sideChain('left', torsoDeg: torsoDeg, thighDeg: thighDeg, hip: hip, knee: knee, shoulder: shoulder,
          elbow: elbow, likelihood: nearLikelihood, noise: noise),
    };

/// Front view for jumping jacks: [arm] is the hip-shoulder-wrist angle, [spread] the ankle
/// distance divided by hip width.
Map<String, Landmark> frontBody({required double arm, required double spread, Noise? noise}) {
  const cx = 200.0, hipY = 300.0, shoulderY = 180.0, hipHalf = 24.0, shoulderHalf = 36.0, armLen = 128.0;
  Landmark p(double x, double y) => Landmark(x + (noise?.next() ?? 0), y + (noise?.next() ?? 0), 0.95);
  final out = <String, Landmark>{'nose': p(cx, shoulderY - 40)};
  for (final sign in [-1.0, 1.0]) {
    final side = sign < 0 ? 'left' : 'right';
    final sx = cx + sign * shoulderHalf;
    final rad = arm * math.pi / 180;
    // Rotate the downward ray (towards the hip) outwards by `arm` degrees.
    final wx = sx + sign * math.sin(rad) * armLen, wy = shoulderY + math.cos(rad) * armLen;
    final ax = cx + sign * spread * hipHalf;
    out['${side}_shoulder'] = p(sx, shoulderY);
    out['${side}_elbow'] = p((sx + wx) / 2, (shoulderY + wy) / 2);
    out['${side}_wrist'] = p(wx, wy);
    out['${side}_hip'] = p(cx + sign * hipHalf, hipY);
    out['${side}_ankle'] = p(ax, hipY + 200);
    out['${side}_knee'] = p((cx + sign * hipHalf + ax) / 2, hipY + 100);
  }
  return out;
}

/// Frames for a sequence of movement cycles. [profile] maps phase 0..1 to a pose; each
/// cycle lasts the matching entry of [cycleMs]; [pauseMs] of rest follows each cycle.
/// [profile] also gets the cycle index (−1 during the lead-in).
List<PoseFrame> cycles(
  List<int> cycleMs,
  Map<String, Landmark> Function(double phase, int cycle) profile, {
  int fps = 30,
  int pauseMs = 300,
  int startMs = 0,
  int leadInMs = 500,
}) {
  final frames = <PoseFrame>[];
  final step = 1000 ~/ fps;
  var t = startMs;
  for (var i = 0; i < leadInMs; i += step) {
    frames.add(PoseFrame(t, profile(0, -1)));
    t += step;
  }
  for (var c = 0; c < cycleMs.length; c++) {
    final ms = cycleMs[c];
    for (var e = 0; e < ms; e += step) {
      frames.add(PoseFrame(t, profile(e / ms, c)));
      t += step;
    }
    for (var e = 0; e < pauseMs; e += step) {
      frames.add(PoseFrame(t, profile(0, c)));
      t += step;
    }
  }
  return frames;
}

/// Smooth rest → peak → rest value for phase 0..1.
double swing(double phase, double rest, double peak) => rest + (peak - rest) * (1 - math.cos(2 * math.pi * phase)) / 2;

/// Human-like tempo: [n] cycles around [baseMs] with ±15% variation.
List<int> humanTempo(int n, int baseMs, {int seed = 1}) {
  final r = math.Random(seed);
  return [for (var i = 0; i < n; i++) (baseMs * (0.85 + r.nextDouble() * 0.3)).round()];
}
