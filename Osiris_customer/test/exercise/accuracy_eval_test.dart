import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/pose_frame.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';

import 'pose_synth.dart';

/// Accuracy evaluation of the rep engine under real-world distortions.
///
/// Every genuine set is replayed at several pose frame rates, landmark jitter levels, body
/// sizes in frame (distance to the phone), phone roll angles and tempos. The false-reject rate
/// is the share of performed reps the engine did not count; the false-accept rate is the share
/// of cheat reps (half range, bouncing, wrong body position) it did count.
///
/// Set OSIRIS_EVAL_REPORT=1 to print the full matrix.

final catalog = loadCatalog();

class Condition {
  final int fps;
  final double jitterPx;
  final double scale; // body size in frame relative to the default skeleton (~300 px tall)
  final double rollDeg;
  final double tempo; // 1.0 = normal; 0.0 = the exercise's fastest legal tempo (see [fastCycleMs])

  const Condition(this.fps, this.jitterPx, this.scale, this.rollDeg, this.tempo);

  @override
  String toString() => '${fps}fps j${jitterPx.toStringAsFixed(0)} s$scale r${rollDeg.toStringAsFixed(0)} t$tempo';
}

typedef Profile = Map<String, Landmark> Function(double phase, int cycle);

class Movement {
  final Profile profile;
  final int cycleMs;
  final int pauseMs;
  final int reps;

  const Movement(this.profile, this.cycleMs, this.pauseMs, this.reps);
}

/// Genuine movement per exercise (same kinematics as the engine unit tests).
final Map<String, Movement> genuine = {
  'pushup': Movement((p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80), 1600, 300, 12),
  'squat': Movement(
      (p, _) => sideBody(torsoDeg: -90 + swing(p, 0, 40), knee: swing(p, 175, 80), hip: swing(p, 175, 85)),
      2200, 300, 12),
  'lunge': Movement((p, leg) {
    final knee = swing(p, 172, 90), hip = swing(p, 175, 100);
    return leg.isEven
        ? sideBody(knee: knee, hip: hip, farKnee: 172, farHip: 175)
        : sideBody(knee: 172, hip: 175, farKnee: knee, farHip: hip);
  }, 2400, 300, 12),
  'situp': Movement((p, _) => sideBody(thighDeg: -40, knee: 70, hip: swing(p, 140, 55)), 2400, 300, 12),
  'jumping_jack': Movement((p, _) => frontBody(arm: swing(p, 20, 165), spread: swing(p, 1.0, 2.2)), 900, 100, 20),
  'high_knees': Movement((p, i) {
    final lift = swing(p, 178, 95), knee = swing(p, 178, 90);
    return i.isEven
        ? sideBody(hip: lift, knee: knee, farHip: 178, farKnee: 178)
        : sideBody(hip: 178, knee: 178, farHip: lift, farKnee: knee);
  }, 600, 60, 24),
};

/// Cheat movement per exercise: reps that must never count.
final Map<String, List<(String, Movement)>> cheats = {
  'pushup': [
    ('half range', Movement((p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 118), shoulder: 80), 1400, 300, 10)),
    ('standing curls', Movement((p, _) => sideBody(torsoDeg: -90, elbow: swing(p, 170, 80), shoulder: 80), 1600, 300, 10)),
    ('bouncing', Movement((p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80), 450, 0, 12)),
  ],
  'squat': [
    ('half range', Movement((p, _) => sideBody(knee: swing(p, 175, 125), hip: swing(p, 175, 130)), 2000, 300, 10)),
    ('lying leg bends', Movement((p, _) => sideBody(torsoDeg: 180, knee: swing(p, 175, 80), hip: swing(p, 175, 95)), 2200, 300, 10)),
  ],
  'lunge': [
    ('half range', Movement((p, _) => sideBody(knee: swing(p, 172, 130)), 2200, 300, 10)),
  ],
  'situp': [
    ('half range', Movement((p, _) => sideBody(thighDeg: -40, knee: 70, hip: swing(p, 140, 95)), 2200, 300, 10)),
    ('standing bends', Movement((p, _) => sideBody(thighDeg: 90, knee: 175, hip: swing(p, 140, 55)), 2400, 300, 10)),
  ],
  'jumping_jack': [
    ('arms only', Movement((p, _) => frontBody(arm: swing(p, 20, 165), spread: 1.0), 900, 100, 15)),
    ('half arms', Movement((p, _) => frontBody(arm: swing(p, 20, 100), spread: swing(p, 1.0, 2.2)), 900, 100, 15)),
  ],
  'high_knees': [
    ('small lifts', Movement((p, _) => sideBody(hip: swing(p, 178, 140), knee: swing(p, 178, 140)), 600, 60, 20)),
    ('lying knee pulls', Movement((p, _) => sideBody(torsoDeg: 180, hip: swing(p, 178, 95), knee: swing(p, 178, 90)), 700, 60, 20)),
  ],
};

/// Applies distance to the phone (scale about the frame centre), phone roll and landmark jitter.
Map<String, Landmark> distort(Map<String, Landmark> lm, Condition c, math.Random rnd) {
  const cx = 200.0, cy = 250.0;
  final r = c.rollDeg * math.pi / 180, cosR = math.cos(r), sinR = math.sin(r);
  double jitter() => (rnd.nextDouble() + rnd.nextDouble() - 1) * c.jitterPx;
  return {
    for (final e in lm.entries)
      e.key: () {
        final dx = (e.value.x - cx) * c.scale, dy = (e.value.y - cy) * c.scale;
        return Landmark(cx + dx * cosR - dy * sinR + jitter(), cy + dx * sinR + dy * cosR + jitter(), e.value.likelihood);
      }(),
  };
}

/// Fastest cycle whose reps are still legal: the time outside the rest zone stays at least 15%
/// above the exercise's minimum rep time even for the quickest rep of the ±15% human variation.
int fastCycleMs(String key, double outOfRestShare) {
  final minRep = catalog.byKey(key)!.minRepS * 1000;
  return (minRep * 1.15 / outOfRestShare / 0.85).ceil();
}

/// Share of a swing cycle spent outside the rest zone, from the swing's rest and peak values.
double outOfRestShare(double restValue, double peakValue, double threshold) {
  final f = ((threshold - restValue) / (peakValue - restValue)).clamp(0.0, 1.0);
  return 1 - 2 * math.acos(1 - 2 * f) / (2 * math.pi);
}

List<PoseFrame> render(Movement m, Condition c, int seed, {int? cycleMs}) {
  final rnd = math.Random(seed);
  final base = c.tempo == 0 ? cycleMs! : m.cycleMs;
  final scale = base / m.cycleMs;
  final tempo = [for (final ms in humanTempo(m.reps, base, seed: seed)) ms];
  return cycles(tempo, (p, i) => distort(m.profile(p, i), c, rnd),
      fps: c.fps, pauseMs: (m.pauseMs * scale).round());
}

/// (rest value, peak value) of each genuine swing, to derive its fastest legal tempo.
const swingRange = {
  'pushup': (170.0, 80.0),
  'squat': (175.0, 80.0),
  'lunge': (172.0, 90.0),
  'situp': (140.0, 55.0),
  'jumping_jack': (20.0, 165.0),
  'high_knees': (178.0, 95.0),
};

int fastestLegalCycleMs(String key) {
  final (rest, peak) = swingRange[key]!;
  return fastCycleMs(key, outOfRestShare(rest, peak, catalog.byKey(key)!.rest.threshold));
}

SessionSummary judge(String key, List<PoseFrame> frames) {
  final engine = RepEngine(catalog.byKey(key)!, catalog);
  for (final f in frames) {
    engine.addFrame(f);
  }
  return engine.finish();
}

/// The supported envelope: landmark jitter up to ~7% of torso length. Beyond it (8 px on a
/// body half the default size, ~13%) the engine must refuse with `unsteady_tracking` rather than
/// count, because a joint angle that noisy cannot tell a full rep from a half rep.
bool inEnvelope(Condition c) => c.jitterPx / c.scale <= 8.0;

/// Plank: seconds of hold credited out of the seconds actually held.
double plankCredit(Condition c, int seed) {
  final rnd = math.Random(seed);
  final step = 1000 ~/ c.fps;
  final engine = RepEngine(catalog.byKey('plank')!, catalog);
  var t = 0;
  for (; t < 2000; t += step) {
    engine.addFrame(PoseFrame(t, distort(sideBody(torsoDeg: -90, hip: 90, knee: 178), c, rnd)));
  }
  final start = t;
  for (; t < start + 30000; t += step) {
    engine.addFrame(
        PoseFrame(t, distort(sideBody(torsoDeg: 190, knee: 178, hip: 176, shoulder: 80, elbow: 90), c, rnd)));
  }
  return engine.finish().holdS / 30.0;
}

const fpsLevels = [30, 15, 10, 7, 5];
const jitterLevels = [1.5, 4.0, 8.0];
const scaleLevels = [0.5, 1.0, 1.3];
const rollLevels = [-12.0, 0.0, 12.0];
const tempoLevels = [1.0, 0.0];

/// Budgets at or above each exercise's `min_pose_fps`.
const minCountedShare = 0.95; // genuine reps counted, over all distortions at one frame rate
const minSetShare = 0.80; // genuine reps counted in any single set
const minPlankCredit = 0.95; // hold seconds credited
const maxRefusedShare = 0.0; // genuine sets refused as unsteady inside the envelope

void main() {
  final report = Platform.environment['OSIRIS_EVAL_REPORT'] == '1';
  final out = StringBuffer();
  tearDownAll(() {
    if (report) stdout.write(out);
  });

  test('genuine reps are counted at every supported frame rate', () {
    out.writeln('Genuine reps counted (%) inside the envelope — columns: pose fps ("·" = below min_pose_fps)');
    out.writeln('exercise      ${fpsLevels.map((f) => '$f'.padLeft(6)).join()}   outside envelope: sets refused / sets');
    final failures = <String>[];
    for (final e in genuine.entries) {
      final minFps = catalog.byKey(e.key)!.minPoseFps;
      final cells = <String>[];
      var outside = 0, refusedOutside = 0;
      for (final fps in fpsLevels) {
        var performed = 0, counted = 0, seed = 0;
        for (final j in jitterLevels) {
          for (final s in scaleLevels) {
            for (final r in rollLevels) {
              for (final t in tempoLevels) {
                final c = Condition(fps, j, s, r, t);
                final sum = judge(e.key, render(e.value, c, ++seed, cycleMs: fastestLegalCycleMs(e.key)));
                final refused = sum.reasons.contains('unsteady_tracking');
                if (!inEnvelope(c)) {
                  if (fps >= minFps) {
                    outside++;
                    if (refused) refusedOutside++;
                  }
                  continue;
                }
                performed += e.value.reps;
                counted += sum.repsValid;
                if (fps < minFps) continue;
                if (refused) failures.add('${e.key} $c: refused as unsteady inside the envelope');
                if (sum.repsValid / e.value.reps < minSetShare) {
                  failures.add('${e.key} $c: ${sum.repsValid}/${e.value.reps} ${sum.reasons}');
                }
              }
            }
          }
        }
        final share = counted / performed;
        if (fps >= minFps && share < minCountedShare) {
          failures.add('${e.key} at $fps fps: ${(100 * share).toStringAsFixed(1)}%');
        }
        cells.add((fps >= minFps ? (100 * share).toStringAsFixed(1) : '·').padLeft(6));
      }
      out.writeln('${e.key.padRight(14)}${cells.join()}   $refusedOutside / $outside');
    }
    expect(failures, isEmpty);
  }, timeout: const Timeout(Duration(minutes: 5)));

  test('plank holds are credited at every supported frame rate', () {
    out.writeln('\nPlank: hold credited (% of 30 s)');
    final cells = <String>[];
    final failures = <String>[];
    for (final fps in fpsLevels) {
      var sum = 0.0, n = 0;
      for (final j in jitterLevels) {
        for (final s in scaleLevels) {
          for (final r in rollLevels) {
            sum += plankCredit(Condition(fps, j, s, r, 1.0), ++n);
          }
        }
      }
      if (sum / n < minPlankCredit) failures.add('plank at $fps fps: ${(100 * sum / n).toStringAsFixed(1)}%');
      cells.add((100 * sum / n).toStringAsFixed(1).padLeft(6));
    }
    out.writeln('plank         ${cells.join()}');
    expect(failures, isEmpty);
  });

  test('cheat reps are never counted, at any frame rate or distortion', () {
    out.writeln('\nCheat reps counted (%) — all frame rates, jitter, body sizes and roll');
    final failures = <String>[];
    for (final e in cheats.entries) {
      for (final (name, m) in e.value) {
        var performed = 0, counted = 0, seed = 1000;
        for (final fps in fpsLevels) {
          for (final j in jitterLevels) {
            for (final s in scaleLevels) {
              for (final r in rollLevels) {
                final n = judge(e.key, render(m, Condition(fps, j, s, r, 1.0), ++seed)).repsValid;
                if (n > 0) failures.add('${e.key} $name ${Condition(fps, j, s, r, 1.0)}: $n counted');
                counted += n;
                performed += m.reps;
              }
            }
          }
        }
        out.writeln('${e.key.padRight(14)}${name.padRight(18)}${(100 * counted / performed).toStringAsFixed(1).padLeft(6)}');
      }
    }
    expect(failures, isEmpty);
  }, timeout: const Timeout(Duration(minutes: 5)));
}
