import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/pose_frame.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';

import 'pose_synth.dart';

final catalog = loadCatalog();

SessionSummary run(String key, List<PoseFrame> frames) {
  final engine = RepEngine(catalog.byKey(key)!, catalog);
  for (final f in frames) {
    engine.addFrame(f);
  }
  return engine.finish();
}

/// Push-up seen from the side: body horizontal, elbow angle swings between [top] and [bottom].
List<PoseFrame> pushups(List<int> tempo, {double top = 170, double bottom = 80, double hip = 178, int seed = 1,
    double torsoDeg = 190, double wristLikelihood = 0.95}) {
  final noise = Noise(seed);
  return cycles(tempo, (p, _) {
    final body = sideBody(torsoDeg: torsoDeg, elbow: swing(p, top, bottom), shoulder: 80, hip: hip, noise: noise);
    if (wristLikelihood < 0.95) {
      for (final s in ['left', 'right']) {
        final w = body['${s}_wrist']!;
        body['${s}_wrist'] = Landmark(w.x, w.y, wristLikelihood);
      }
    }
    return body;
  });
}

void main() {
  test('bundled catalog parses and lists every exercise', () {
    expect(catalog.rulesVersion, 'exercise-rules-v2');
    expect(catalog.exercises.map((e) => e.key),
        ['pushup', 'squat', 'lunge', 'situp', 'jumping_jack', 'high_knees', 'plank']);
    expect(catalog.sessionRules.hardReasons, contains('no_valid_reps'));
  });

  group('push-up', () {
    test('genuine reps with human tempo are verified', () {
      final s = run('pushup', pushups(humanTempo(12, 1600)));
      expect(s.repsValid, 12);
      expect(s.repsAttempted, 12);
      expect(s.verdict, 'verified', reason: '${s.reasons}');
      expect(s.formScore, greaterThan(0.9));
      expect(s.validRepDurationsS.every((d) => d >= 0.6 && d <= 8), isTrue);
    });

    test('half reps never count', () {
      final s = run('pushup', pushups(humanTempo(8, 1400), bottom: 118));
      expect(s.repsValid, 0);
      expect(s.reasons, containsAll(['partial_range', 'no_valid_reps']));
      expect(s.verdict, 'rejected');
    });

    test('tiny wobbles are not attempts', () {
      final s = run('pushup', pushups(humanTempo(8, 1400), bottom: 140));
      expect(s.repsAttempted, 0);
      expect(s.verdict, 'rejected');
    });

    test('bouncing faster than humanly controlled is too_fast', () {
      final s = run('pushup', pushups(List.filled(10, 450), seed: 2));
      expect(s.repsValid, 0);
      expect(s.reasons, contains('too_fast'));
      expect(s.verdict, 'rejected');
    });

    test('sagging hips break form', () {
      final s = run('pushup', pushups(humanTempo(8, 1600), hip: 125, torsoDeg: 205));
      expect(s.repsValid, 0);
      expect(s.reasons, contains('form_break'));
    });

    test('arm curls while standing are not push-ups', () {
      final s = run('pushup', pushups(humanTempo(8, 1600), torsoDeg: -90));
      expect(s.repsValid, 0);
      expect(s.reasons, contains('wrong_position'));
      expect(s.verdict, 'rejected');
    });

    test('hidden wrists produce no reps', () {
      final s = run('pushup', pushups(humanTempo(8, 1600), wristLikelihood: 0.2));
      expect(s.repsAttempted, 0);
      expect(s.verdict, 'rejected');
    });

    test('a tracker that teleports joints is a glitch, not a rep', () {
      final noise = Noise(3);
      final frames = <PoseFrame>[];
      var t = 0;
      for (var i = 0; i < 400; i++) {
        // Alternates between two unrelated detections every few frames.
        final elbow = (i ~/ 3).isEven ? 170.0 : 70.0;
        frames.add(PoseFrame(t, sideBody(torsoDeg: 190, elbow: elbow, shoulder: 80, noise: noise)));
        t += 33;
      }
      final s = run('pushup', frames);
      expect(s.repsValid, 0);
      expect(s.verdict, 'rejected');
    });

    test('machine-identical timing is flagged as a replay', () {
      final s = run('pushup', pushups(List.filled(10, 1500)));
      expect(s.repsValid, 10);
      expect(s.reasons, contains('replay_suspected'));
      expect(s.verdict, 'review');
    });

    test('mostly-bad sets go to review', () {
      final good = pushups(humanTempo(3, 1600));
      final bad = pushups(humanTempo(6, 1400), bottom: 118, seed: 4);
      final shifted = [for (final f in bad) PoseFrame(f.tMs + good.last.tMs + 33, f.landmarks)];
      final s = run('pushup', [...good, ...shifted]);
      expect(s.repsValid, 3);
      expect(s.reasons, contains('low_valid_ratio'));
      expect(s.verdict, 'review');
    });

    test('live updates count reps and coach the player', () {
      final engine = RepEngine(catalog.byKey('pushup')!, catalog);
      final updates = [for (final f in pushups(humanTempo(3, 1600))) engine.addFrame(f)];
      expect(updates.last.validReps, 3);
      expect(updates.where((u) => u.newRep != null).length, 3);
      expect(updates.map((u) => u.hint), contains('Go lower'));
      expect(updates.map((u) => u.hint), contains('Nice rep'));
    });
  });

  test('squats count; folding the torso breaks form', () {
    final noise = Noise(5);
    List<PoseFrame> squats(double hipBottom, double lean) => cycles(humanTempo(10, 2200),
        (p, _) => sideBody(torsoDeg: -90 + swing(p, 0, lean), knee: swing(p, 175, 80), hip: swing(p, 175, hipBottom),
            noise: noise));
    final good = run('squat', squats(85, 40));
    expect(good.repsValid, 10);
    expect(good.verdict, 'verified', reason: '${good.reasons}');
    final folded = run('squat', squats(35, 90));
    expect(folded.repsValid, 0);
    // Rejected either by the hip angle (form) or because the torso is no longer upright (position).
    expect(folded.reasons.toSet().intersection({'form_break', 'wrong_position'}), isNotEmpty);
  });

  test('alternating lunges count each leg', () {
    final noise = Noise(6);
    final frames = cycles(humanTempo(10, 2400), (p, leg) {
      final knee = swing(p, 172, 90), hip = swing(p, 175, 100);
      return leg.isEven
          ? sideBody(knee: knee, hip: hip, farKnee: 172, farHip: 175, noise: noise)
          : sideBody(knee: 172, hip: 175, farKnee: knee, farHip: hip, noise: noise);
    });
    final s = run('lunge', frames);
    expect(s.repsValid, 10);
    expect(s.verdict, 'verified', reason: '${s.reasons}');
  });

  test('sit-ups count when lying down', () {
    final noise = Noise(7);
    final frames = cycles(humanTempo(10, 2400),
        (p, _) => sideBody(thighDeg: -40, knee: 70, hip: swing(p, 140, 55), noise: noise));
    final s = run('situp', frames);
    expect(s.repsValid, 10, reason: '${s.reasons}');
    expect(s.verdict, 'verified');
  });

  test('jumping jacks need arms up and legs apart', () {
    final noise = Noise(8);
    final good = run('jumping_jack',
        cycles(humanTempo(15, 900), (p, _) => frontBody(arm: swing(p, 20, 165), spread: swing(p, 1.0, 2.2), noise: noise),
            pauseMs: 100));
    expect(good.repsValid, 15);
    expect(good.verdict, 'verified', reason: '${good.reasons}');
    final armsOnly = run('jumping_jack',
        cycles(humanTempo(15, 900), (p, _) => frontBody(arm: swing(p, 20, 165), spread: 1.0, noise: noise), pauseMs: 100));
    expect(armsOnly.repsValid, 0);
    expect(armsOnly.reasons, contains('form_break'));
  });

  test('high knees count each lift', () {
    final noise = Noise(9);
    final frames = cycles(humanTempo(20, 600), (p, i) {
      final lift = swing(p, 178, 95), knee = swing(p, 178, 90);
      return i.isEven
          ? sideBody(hip: lift, knee: knee, farHip: 178, farKnee: 178, noise: noise)
          : sideBody(hip: 178, knee: 178, farHip: lift, farKnee: knee, noise: noise);
    }, pauseMs: 60);
    final s = run('high_knees', frames);
    expect(s.repsValid, 20, reason: '${s.reasons}');
    expect(s.verdict, 'verified');
  });

  group('plank', () {
    List<PoseFrame> plank({required bool sitFirst, required int holdMs, Noise? noise}) {
      final frames = <PoseFrame>[];
      var t = 0;
      if (sitFirst) {
        for (; t < 2000; t += 33) {
          frames.add(PoseFrame(t, sideBody(torsoDeg: -90, hip: 90, knee: 178, noise: noise)));
        }
      }
      final end = t + holdMs;
      for (; t < end; t += 33) {
        frames.add(PoseFrame(t, sideBody(torsoDeg: 190, knee: 178, hip: 176, shoulder: 80, elbow: 90, noise: noise)));
      }
      return frames;
    }

    test('a hold entered from sitting is timed and verified', () {
      final s = run('plank', plank(sitFirst: true, holdMs: 30000, noise: Noise(10)));
      expect(s.holdS, closeTo(30, 0.5));
      expect(s.verdict, 'verified', reason: '${s.reasons}');
    });

    test('starting already in the plank is not trusted', () {
      final s = run('plank', plank(sitFirst: false, holdMs: 30000, noise: Noise(11)));
      expect(s.reasons, contains('no_entry_transition'));
      expect(s.verdict, 'rejected');
    });

    test('a perfectly frozen pose is static, not a person', () {
      final s = run('plank', plank(sitFirst: true, holdMs: 30000));
      expect(s.reasons, contains('static_pose'));
      expect(s.verdict, 'rejected');
    });

    test('standing straight is not a plank', () {
      final noise = Noise(12);
      final frames = <PoseFrame>[
        for (var t = 0; t < 2000; t += 33) PoseFrame(t, sideBody(knee: 90, hip: 100, noise: noise)),
        for (var t = 2000; t < 32000; t += 33) PoseFrame(t, sideBody(noise: noise)),
      ];
      final s = run('plank', frames);
      expect(s.holdS, 0);
      expect(s.reasons, contains('hold_too_short'));
    });
  });

  group('frame rate and tracking noise (catalog v2)', () {
    test('a tracker too unsteady to judge is refused with a reason, never counted', () {
      // ~16 px of jitter on a 60 px forearm: a half rep and a full rep look alike.
      final noise = Noise(31, px: 16);
      final frames = cycles(humanTempo(10, 1600),
          (p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 118), shoulder: 80, noise: noise));
      final s = run('pushup', frames);
      expect(s.repsValid, 0);
      expect(s.reasons, contains('unsteady_tracking'));
      expect(s.verdict, 'rejected');
    });

    test('steady tracking is never called unsteady', () {
      final s = run('pushup', pushups(humanTempo(12, 1600)));
      expect(s.reasons, isNot(contains('unsteady_tracking')));
      expect(s.repsValid, 12);
    });

    test('high knees at 10 fps still count every lift (smoothing is per second, not per frame)', () {
      final noise = Noise(32);
      final frames = cycles(humanTempo(16, 600), (p, i) {
        final lift = swing(p, 178, 95), knee = swing(p, 178, 90);
        return i.isEven
            ? sideBody(hip: lift, knee: knee, farHip: 178, farKnee: 178, noise: noise)
            : sideBody(hip: 178, knee: 178, farHip: lift, farKnee: knee, noise: noise);
      }, fps: 10, pauseMs: 60);
      expect(run('high_knees', frames).repsValid, 16);
    });

    test('rep durations are interpolated between frames, not snapped to the frame grid', () {
      // Identical 1.5 s cycles at 7 fps (143 ms frames): snapped durations would jump by a frame.
      final frames = cycles(List.filled(6, 1500),
          (p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80), fps: 7, pauseMs: 400);
      final durations = run('pushup', frames).validRepDurationsS;
      expect(durations, hasLength(6));
      final spread = durations.reduce(math.max) - durations.reduce(math.min);
      expect(spread, lessThan(0.06), reason: '$durations');
    });
  });

  test('duration CV matches the server formula', () {
    expect(durationCv([1, 1, 1]), 0);
    expect(durationCv([1]), 1.0);
    expect(durationCv([1, 3]), closeTo(0.5, 1e-9));
  });

  test('per-frame cost stays far below the camera frame budget', () {
    final frames = pushups(humanTempo(300, 1600));
    final engine = RepEngine(catalog.byKey('pushup')!, catalog);
    final sw = Stopwatch()..start();
    for (final f in frames) {
      engine.addFrame(f);
    }
    sw.stop();
    final usPerFrame = sw.elapsedMicroseconds / frames.length;
    // 33 ms is the budget at 30 fps; the engine must use a tiny fraction of it.
    expect(usPerFrame, lessThan(200), reason: '${usPerFrame.toStringAsFixed(1)} µs/frame over ${frames.length} frames');
    expect(engine.finish().repsValid, 300);
  });
}
