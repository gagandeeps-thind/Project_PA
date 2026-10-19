// Replays the Kotlin parity corpus through the Dart rep engine and compares verdicts.
// Run via tools/parity/check_engine_parity.sh; exits 1 on any difference.
import 'dart:convert';
import 'dart:io';

import '../../Osiris_customer/lib/exercise/exercise_catalog.dart';
import '../../Osiris_customer/lib/exercise/pose_frame.dart';
import '../../Osiris_customer/lib/exercise/rep_engine.dart';

void main(List<String> args) {
  final root = args.isEmpty ? '.' : args.first;
  final catalog = ExerciseCatalog.parse(File('$root/Osiris_customer/assets/exercise_catalog.json').readAsStringSync());
  final parity = '$root/shared/domain/build/parity';
  final expected = jsonDecode(File('$parity/kotlin_results.json').readAsStringSync()) as List;
  var mismatches = 0;
  for (final raw in expected) {
    final k = raw as Map<String, dynamic>;
    final rec = jsonDecode(File('$parity/inputs/${k['file']}').readAsStringSync()) as Map<String, dynamic>;
    final engine = RepEngine(catalog.byKey(rec['exercise_key'] as String)!, catalog);
    for (final f in rec['frames'] as List) {
      final lm = <String, Landmark>{
        for (final e in ((f as Map)['l'] as Map).entries)
          e.key as String: Landmark(((e.value as List)[0] as num).toDouble(), ((e.value as List)[1] as num).toDouble(),
              ((e.value as List)[2] as num).toDouble()),
      };
      engine.addFrame(PoseFrame(f['t'] as int, lm));
    }
    final s = engine.finish();
    final dart = {
      'reps_valid': s.repsValid,
      'reps_attempted': s.repsAttempted,
      'hold_s': s.holdS,
      'form_score': s.formScore,
      'verdict': s.verdict,
      'reasons': s.reasons,
      'rep_durations_ms': [for (final r in s.reps) r.durationMs],
    };
    final diffs = <String>[];
    for (final key in dart.keys) {
      final a = jsonEncode(k[key]), b = jsonEncode(dart[key]);
      final numeric = k[key] is num && dart[key] is num;
      if (numeric ? ((k[key] as num) - (dart[key] as num)).abs() > 1e-9 : a != b) diffs.add('$key kotlin=$a dart=$b');
    }
    if (diffs.isNotEmpty) {
      mismatches++;
      stdout.writeln('MISMATCH ${k['name']}: ${diffs.join('; ')}');
    }
  }
  stdout.writeln('${expected.length - mismatches}/${expected.length} cases identical');
  exit(mismatches == 0 ? 0 : 1);
}
