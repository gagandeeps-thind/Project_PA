import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/pose_frame.dart';
import 'package:osiris_customer/exercise/pose_recording.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';

import 'pose_synth.dart';

/// Replays every QA landmark recording in test/exercise/recordings/ through the rep engine and
/// compares the result with the tester's label. Each device QA session that saves a recording
/// adds a permanent regression case. Format and retrieval: recordings/README.md.
final catalog = loadCatalog();

SessionSummary replay(PoseRecording r) {
  final engine = RepEngine(catalog.byKey(r.exerciseKey)!, catalog);
  for (final f in r.frames) {
    engine.addFrame(f);
  }
  return engine.finish();
}

/// Reps may be off by one at either end of a set (a tester's first or last rep is often
/// borderline); holds by two seconds.
void expectMatchesLabel(PoseRecording r, SessionSummary s, String name) {
  if (r.labelReps != null) {
    expect((s.repsValid - r.labelReps!).abs(), lessThanOrEqualTo(1),
        reason: '$name: counted ${s.repsValid}, label ${r.labelReps} (${s.reasons})');
  }
  if (r.labelHoldS != null) {
    expect((s.holdS - r.labelHoldS!).abs(), lessThanOrEqualTo(2.0),
        reason: '$name: held ${s.holdS.toStringAsFixed(1)} s, label ${r.labelHoldS} s');
  }
}

void main() {
  test('a recording round-trips through its JSON format and replays identically', () {
    final noise = Noise(41);
    final recorder = PoseRecorder();
    final frames = cycles(humanTempo(8, 1600),
        (p, _) => sideBody(torsoDeg: 190, elbow: swing(p, 170, 80), shoulder: 80, noise: noise));
    frames.forEach(recorder.add);
    final original = recorder.finish(exerciseKey: 'pushup', rulesVersion: catalog.rulesVersion, labelReps: 8);
    final restored = PoseRecording.fromJson(jsonDecode(jsonEncode(original.toJson())) as Map<String, dynamic>);

    expect(restored.frames, hasLength(frames.length));
    expect(restored.labelReps, 8);
    final a = replay(original), b = replay(restored);
    // Stored coordinates are rounded to 0.1 px; the count must not depend on that.
    expect(b.repsValid, a.repsValid);
    expectMatchesLabel(restored, b, 'round-trip');
  });

  test('the recorder stops at its cap instead of growing without bound', () {
    final recorder = PoseRecorder();
    for (var i = 0; i < PoseRecorder.maxFrames + 10; i++) {
      recorder.add(PoseFrame(i, const {}));
    }
    expect(recorder.frames, hasLength(PoseRecorder.maxFrames));
  });

  test('an unknown format is refused, not misread', () {
    expect(() => PoseRecording.fromJson({'format': 'osiris-pose-v0'}), throwsFormatException);
  });

  final files = Directory('test/exercise/recordings').listSync().whereType<File>()
      .where((f) => f.path.endsWith('.json')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  test('the recordings folder is not empty', () => expect(files, isNotEmpty));
  for (final file in files) {
    final name = file.uri.pathSegments.last;
    test('replay $name matches its label', () {
      final r = PoseRecording.fromJson(jsonDecode(file.readAsStringSync()) as Map<String, dynamic>);
      expect(catalog.byKey(r.exerciseKey), isNotNull, reason: 'unknown exercise ${r.exerciseKey}');
      expect(r.labelReps ?? r.labelHoldS, isNotNull, reason: 'an unlabeled recording tests nothing');
      expectMatchesLabel(r, replay(r), name);
    });
  }
}
