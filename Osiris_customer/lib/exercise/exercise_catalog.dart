import 'dart:convert';

/// A zone bound on the tracked metric: values `above` or `below` a threshold are inside.
class Zone {
  final double? above;
  final double? below;

  const Zone({this.above, this.below});

  factory Zone.fromJson(Map<String, dynamic> j) =>
      Zone(above: (j['above'] as num?)?.toDouble(), below: (j['below'] as num?)?.toDouble());

  bool contains(double v) => (above == null || v > above!) && (below == null || v < below!);

  double get threshold => (above ?? below)!;
}

/// A form rule checked while a rep is in progress:
/// - `angle`: the angle at the middle of three [joints] must stay above [min];
/// - `ankle_spread`: ankle distance in torso lengths (median over the rep's peak frames) must reach [min];
/// - `orientation`: the segment between two [joints] must stay within [maxDeg] of [axis].
class FormRule {
  final String code;
  final String type;
  final List<String> joints;
  final double min;
  final String axis;
  final double maxDeg;

  const FormRule({
    required this.code,
    required this.type,
    required this.joints,
    this.min = 0,
    this.axis = 'vertical',
    this.maxDeg = 90,
  });

  factory FormRule.fromJson(Map<String, dynamic> j) => FormRule(
        code: j['code'] as String,
        type: j['type'] as String? ?? 'angle',
        joints: (j['joints'] as List? ?? const []).cast<String>(),
        min: (j['min'] as num?)?.toDouble() ?? 0,
        axis: j['axis'] as String? ?? 'vertical',
        maxDeg: (j['max_deg'] as num?)?.toDouble() ?? 90,
      );
}

/// One exercise from the server catalog (`GET /api/v2/exercises`, bundled as an asset).
class ExerciseSpec {
  final String key;
  final String name;
  final String kind; // reps | hold
  final String camera; // side | front
  final String instructions;
  final List<String> joints;
  final String sides; // best | min | mean
  final Zone rest;
  final Zone peak;
  final List<FormRule> form;
  final double minRepS;
  final double maxRepS;
  final int maxRepsPerMin;
  final double maxHoldS;
  /// Slowest pose stream (frames per second) the engine counts this exercise reliably at.
  final double minPoseFps;

  const ExerciseSpec({
    required this.key,
    required this.name,
    required this.kind,
    required this.camera,
    required this.instructions,
    required this.joints,
    required this.sides,
    required this.rest,
    required this.peak,
    required this.form,
    required this.minRepS,
    required this.maxRepS,
    required this.maxRepsPerMin,
    required this.maxHoldS,
    this.minPoseFps = 5,
  });

  bool get isHold => kind == 'hold';

  factory ExerciseSpec.fromJson(Map<String, dynamic> j) {
    final metric = j['metric'] as Map<String, dynamic>;
    return ExerciseSpec(
      key: j['key'] as String,
      name: j['name'] as String,
      kind: j['kind'] as String,
      camera: j['camera'] as String,
      instructions: j['instructions'] as String? ?? '',
      joints: (metric['joints'] as List).cast<String>(),
      sides: metric['sides'] as String? ?? 'best',
      rest: Zone.fromJson(j['rest'] as Map<String, dynamic>),
      peak: Zone.fromJson(j['peak'] as Map<String, dynamic>),
      form: (j['form'] as List? ?? const []).map((f) => FormRule.fromJson(f as Map<String, dynamic>)).toList(),
      minRepS: (j['min_rep_s'] as num).toDouble(),
      maxRepS: (j['max_rep_s'] as num).toDouble(),
      maxRepsPerMin: (j['max_reps_per_min'] as num).toInt(),
      maxHoldS: (j['max_hold_s'] as num?)?.toDouble() ?? 0,
      minPoseFps: (j['min_pose_fps'] as num?)?.toDouble() ?? 5,
    );
  }
}

/// Session-level rules, applied on the device exactly as the server re-check applies them.
class SessionRules {
  final double minValidRatio;
  final int replayMinReps;
  final double replayMaxDurationCv;
  final double minHoldS;
  final double maxSessionS;
  final Set<String> hardReasons;

  const SessionRules({
    required this.minValidRatio,
    required this.replayMinReps,
    required this.replayMaxDurationCv,
    required this.minHoldS,
    required this.maxSessionS,
    required this.hardReasons,
  });

  factory SessionRules.fromJson(Map<String, dynamic> j) => SessionRules(
        minValidRatio: (j['min_valid_ratio'] as num).toDouble(),
        replayMinReps: (j['replay_min_reps'] as num).toInt(),
        replayMaxDurationCv: (j['replay_max_duration_cv'] as num).toDouble(),
        minHoldS: (j['min_hold_s'] as num).toDouble(),
        maxSessionS: (j['max_session_s'] as num).toDouble(),
        hardReasons: (j['hard_reasons'] as List).cast<String>().toSet(),
      );
}

class ExerciseCatalog {
  final String rulesVersion;
  final double minLikelihood;
  final SessionRules sessionRules;
  final List<ExerciseSpec> exercises;

  const ExerciseCatalog({
    required this.rulesVersion,
    required this.minLikelihood,
    required this.sessionRules,
    required this.exercises,
  });

  factory ExerciseCatalog.fromJson(Map<String, dynamic> j) => ExerciseCatalog(
        rulesVersion: j['rules_version'] as String,
        minLikelihood: (j['min_landmark_likelihood'] as num).toDouble(),
        sessionRules: SessionRules.fromJson(j['session_rules'] as Map<String, dynamic>),
        exercises: (j['exercises'] as List).map((e) => ExerciseSpec.fromJson(e as Map<String, dynamic>)).toList(),
      );

  factory ExerciseCatalog.parse(String source) =>
      ExerciseCatalog.fromJson(jsonDecode(source) as Map<String, dynamic>);

  ExerciseSpec? byKey(String key) {
    for (final e in exercises) {
      if (e.key == key) return e;
    }
    return null;
  }
}
