import 'dart:math' as math;

import 'exercise_catalog.dart';
import 'pose_frame.dart';

/// Where the player is in the current rep.
enum RepPhase { waiting, rest, moving, holding }

/// One completed (or abandoned) rep.
class RepResult {
  final int index;
  final int startMs;
  final int durationMs;
  final double peakValue;
  final bool valid;
  final String? reason;

  const RepResult({
    required this.index,
    required this.startMs,
    required this.durationMs,
    required this.peakValue,
    required this.valid,
    this.reason,
  });
}

/// Live state for the camera screen, produced per frame.
class EngineUpdate {
  final int validReps;
  final int attemptedReps;
  final double holdS;
  final RepPhase phase;
  final double? metric;
  final bool visible;
  final String hint;
  final RepResult? newRep;

  const EngineUpdate({
    required this.validReps,
    required this.attemptedReps,
    required this.holdS,
    required this.phase,
    required this.metric,
    required this.visible,
    required this.hint,
    this.newRep,
  });
}

/// The device's verdict on one set; uploaded to `POST /api/v2/exercise-sessions`.
class SessionSummary {
  final String exerciseKey;
  final String rulesVersion;
  final double durationS;
  final int repsAttempted;
  final int repsValid;
  final double holdS;
  final double formScore;
  final String verdict; // verified | review | rejected
  final List<String> reasons;
  final List<RepResult> reps;

  const SessionSummary({
    required this.exerciseKey,
    required this.rulesVersion,
    required this.durationS,
    required this.repsAttempted,
    required this.repsValid,
    required this.holdS,
    required this.formScore,
    required this.verdict,
    required this.reasons,
    required this.reps,
  });

  List<double> get validRepDurationsS =>
      [for (final r in reps) if (r.valid) r.durationMs / 1000.0];
}

/// Counts reps (or a timed hold) from a stream of poses and judges whether they are genuine.
///
/// Per frame: the tracked joint angle is computed from the side the camera sees best, lightly
/// smoothed, and run through a rest → moving → rest state machine. A rep counts only if it
/// reached the peak zone, took a humanly possible time, kept form, stayed visible, and its
/// limb lengths stayed stable (a tracker that jumps between people or glitches changes them).
/// At the end, session rules shared with the server flag machine-regular timing (a replayed
/// video), implausible rates and low valid ratios. Cost is O(1) per frame.
class RepEngine {
  final ExerciseSpec spec;
  final ExerciseCatalog catalog;

  RepEngine(this.spec, this.catalog);

  // Smoothing is a time constant, not a per-frame weight, so a 5 fps phone and a 30 fps phone
  // see the same lag (a per-frame weight averaged the peak away at low frame rates).
  static const double _smoothingTauMs = 45;
  // Faster than any human joint: a single-frame jump this large is a tracking glitch.
  static const double _maxDegPerSecond = 1000;
  // ...and only when the jump is large in absolute terms: landmark jitter divided by a short
  // frame interval is also "fast", but it never moves a joint angle this far in one frame.
  static const double _minGlitchJumpDeg = 60;
  static const double _maxInvisibleFraction = 0.3;
  static const double _maxFormBreakFraction = 0.2;
  static const double _maxBoneCv = 0.3;
  // Below this landmark spread (in torso lengths) the pose is frozen: injected or a still image.
  static const double _minLivenessStd = 0.001;
  // Out-of-zone wobble shorter than this does not end a hold.
  static const int _holdGraceMs = 600;
  // Tracking noise: variation of the tracked limbs' lengths while the player is still at the
  // top of a rep. Limbs are rigid and not rotating then, so the variation is the tracker's own
  // jitter. Joint-angle noise is about 57.3 degrees x that coefficient of variation; telling a
  // full rep from one stopping 15 degrees short at 3 sigma needs <= 5 degrees, i.e. CV <= 0.087.
  // 0.08 leaves margin (accuracy evaluation: <= 0.069 in the supported envelope).
  static const double _maxRestLimbCv = 0.08;
  static const int _minRestSamples = 15;

  RepPhase _phase = RepPhase.waiting;
  String? _side;
  double? _smoothed;
  final _restLimbs = {for (final side in ['left', 'right']) side: (_Stats(), _Stats())};
  // Previous smoothed value and its time, to interpolate when the angle crossed a zone edge.
  double? _prevV;
  int? _prevMs;
  double? _lastRaw;
  int? _lastRawMs;
  int? _firstMs;
  int _lastMs = 0;

  // Current rep accumulators.
  int _repStartMs = 0;
  bool _reachedPeak = false;
  double _peakValue = 0;
  int _repFrames = 0;
  int _repInvisible = 0;
  int _repFormBreaks = 0;
  int _repWrongPosition = 0;
  int _repGlitches = 0;
  final _peakSpreads = <double>[];
  final _bone1 = _Stats();
  final _bone2 = _Stats();

  final List<RepResult> _reps = [];
  int _valid = 0;
  int _visibleFrames = 0;
  int _frames = 0;

  // Hold state.
  bool _sawRest = false;
  bool _enteredWithoutRest = false;
  bool _everHeld = false;
  int _holdMs = 0;
  int? _holdLastInMs;
  final _holdHipX = _Stats();
  final _holdHipY = _Stats();

  String _hint = '';

  List<RepResult> get reps => List.unmodifiable(_reps);

  EngineUpdate addFrame(PoseFrame frame) {
    _firstMs ??= frame.tMs;
    _frames++;
    _lastMs = frame.tMs;
    final raw = _metric(frame);
    RepResult? newRep;

    if (raw == null) {
      _hint = 'Move so your whole body is in view';
      if (_phase == RepPhase.moving) {
        _repFrames++;
        _repInvisible++;
      }
      return _update(null, false, null);
    }
    _visibleFrames++;

    if (_lastRaw != null && _lastRawMs != null && frame.tMs > _lastRawMs!) {
      final speed = (raw - _lastRaw!).abs() / ((frame.tMs - _lastRawMs!) / 1000.0);
      final jump = (raw - _lastRaw!).abs();
      if (jump >= _minGlitchJumpDeg && speed > _maxDegPerSecond && _phase == RepPhase.moving) _repGlitches++;
    }
    final dtMs = _lastRawMs == null ? 0 : frame.tMs - _lastRawMs!;
    _lastRaw = raw;
    _lastRawMs = frame.tMs;
    final alpha = 1 - math.exp(-math.max(dtMs, 0) / _smoothingTauMs);
    final v = _smoothed = _smoothed == null ? raw : _smoothed! + alpha * (raw - _smoothed!);

    if (spec.isHold) {
      _hold(frame, v);
      return _update(v, true, null);
    }

    switch (_phase) {
      case RepPhase.waiting:
        _hint = 'Get into the start position';
        if (spec.rest.contains(v)) _phase = RepPhase.rest;
      case RepPhase.rest:
        _sampleRestLimbs(frame);
        _hint = _valid == 0 ? 'Start when ready' : 'Keep going';
        if (!spec.rest.contains(v)) _startRep(_crossingMs(frame.tMs, v), v);
      case RepPhase.moving:
        _accumulate(frame, v);
        if (spec.rest.contains(v)) {
          newRep = _finishRep(_crossingMs(frame.tMs, v));
          _phase = RepPhase.rest;
        } else if (frame.tMs - _repStartMs > spec.maxRepS * 1500) {
          newRep = _record(frame.tMs, false, 'too_slow');
          _hint = 'Rep took too long. Reset to the start position';
          _phase = RepPhase.waiting;
        }
      case RepPhase.holding:
        break;
    }
    _prevV = v;
    _prevMs = frame.tMs;
    return _update(v, true, newRep);
  }

  SessionSummary finish() {
    final rules = catalog.sessionRules;
    final durationS = _firstMs == null ? 0.0 : (_lastMs - _firstMs!) / 1000.0;
    final reasons = <String>[];
    final attempted = _reps.length;
    var holdS = 0.0;

    if (spec.isHold) {
      _closeHold(_lastMs);
      holdS = math.min(_holdMs / 1000.0, spec.maxHoldS);
      if (_enteredWithoutRest) reasons.add('no_entry_transition');
      if (holdS < rules.minHoldS) reasons.add('hold_too_short');
      final spread = _holdHipX.std + _holdHipY.std;
      if (_holdHipX.n >= 10 && spread < _minLivenessStd) reasons.add('static_pose');
    } else {
      if (_unsteady && _valid > 0) {
        // Reps counted before enough still frames were seen cannot be trusted either.
        for (var i = 0; i < _reps.length; i++) {
          final r = _reps[i];
          if (r.valid) {
            _reps[i] = RepResult(index: r.index, startMs: r.startMs, durationMs: r.durationMs,
                peakValue: r.peakValue, valid: false, reason: 'unsteady_tracking');
          }
        }
        _valid = 0;
      }
      for (final r in _reps) {
        if (!r.valid && r.reason != null) reasons.add(r.reason!);
      }
      if (_valid == 0) {
        reasons.add('no_valid_reps');
      } else if (_valid / math.max(attempted, 1) < rules.minValidRatio) {
        reasons.add('low_valid_ratio');
      }
      final durations = [for (final r in _reps) if (r.valid) r.durationMs / 1000.0];
      if (durations.length >= rules.replayMinReps && durationCv(durations) < rules.replayMaxDurationCv) {
        reasons.add('replay_suspected');
      }
      if (durationS > 0 && _valid / (durationS / 60.0) > spec.maxRepsPerMin) reasons.add('rate_implausible');
    }

    final unique = reasons.toSet().toList();
    final hard = unique.any(rules.hardReasons.contains);
    // Rep-level reasons on rejected reps are evidence, not a session failure on their own.
    final repLevel = {
      'too_fast', 'too_slow', 'form_break', 'wrong_position', 'low_visibility', 'tracking_glitch', 'partial_range',
      'unsteady_tracking',
    };
    final soft = unique.where((r) => !repLevel.contains(r)).isNotEmpty;
    final verdict = hard ? 'rejected' : (soft ? 'review' : 'verified');
    final visibility = _frames == 0 ? 0.0 : _visibleFrames / _frames;
    final quality = spec.isHold ? (holdS > 0 ? 1.0 : 0.0) : (attempted == 0 ? 0.0 : _valid / attempted);

    return SessionSummary(
      exerciseKey: spec.key,
      rulesVersion: catalog.rulesVersion,
      durationS: durationS,
      repsAttempted: attempted,
      repsValid: _valid,
      holdS: holdS,
      formScore: double.parse((quality * visibility).toStringAsFixed(3)),
      verdict: verdict,
      reasons: unique,
      reps: List.unmodifiable(_reps),
    );
  }

  // ── metric ───────────────────────────────────────────────────────────

  double? _metric(PoseFrame f) {
    final j = spec.joints;
    double? sideAngle(String side) {
      final a = f.get(side, j[0]), b = f.get(side, j[1]), c = f.get(side, j[2]);
      if (a == null || b == null || c == null) return null;
      final minLik = catalog.minLikelihood;
      if (a.likelihood < minLik || b.likelihood < minLik || c.likelihood < minLik) return null;
      return angleDeg(a, b, c);
    }

    final left = sideAngle('left'), right = sideAngle('right');
    switch (spec.sides) {
      case 'mean':
        return (left == null || right == null) ? null : (left + right) / 2;
      case 'min':
        if (left == null) return right;
        if (right == null) return left;
        return math.min(left, right);
      default:
        _side = _pickSide(f, left != null, right != null);
        return _side == 'left' ? left : (_side == 'right' ? right : null);
    }
  }

  /// The side the camera sees best, sticky so the angle does not flip between sides.
  String? _pickSide(PoseFrame f, bool leftOk, bool rightOk) {
    if (!leftOk && !rightOk) return null;
    if (!rightOk) return 'left';
    if (!leftOk) return 'right';
    double score(String side) => spec.joints.fold(0.0, (s, j) => s + (f.get(side, j)?.likelihood ?? 0));
    final l = score('left'), r = score('right');
    if (_side == null) return l >= r ? 'left' : 'right';
    final other = _side == 'left' ? 'right' : 'left';
    final margin = 0.15 * spec.joints.length;
    return (_side == 'left' ? r - l : l - r) > margin ? other : _side;
  }

  double? _torso(PoseFrame f, String side) {
    final s = f.get(side, 'shoulder'), h = f.get(side, 'hip');
    if (s == null || h == null) return null;
    final d = s.distanceTo(h);
    return d > 0 ? d : null;
  }

  // ── reps ─────────────────────────────────────────────────────────────

  void _sampleRestLimbs(PoseFrame f) {
    final j = spec.joints;
    for (final side in _restLimbs.keys) {
      final a = f.get(side, j[0]), b = f.get(side, j[1]), c = f.get(side, j[2]);
      final minLik = catalog.minLikelihood;
      if (a == null || b == null || c == null) continue;
      if (a.likelihood < minLik || b.likelihood < minLik || c.likelihood < minLik) continue;
      final (s1, s2) = _restLimbs[side]!;
      s1.add(a.distanceTo(b));
      s2.add(b.distanceTo(c));
    }
  }

  /// True once enough still frames show the tracker is too noisy to judge reps. Exercises that
  /// read the better-tracked side are bounded by the steadier side; exercises that read both sides
  /// (lunges, high knees, jumping jacks) by the noisier one, since its errors reach the metric too.
  bool get _unsteady {
    final cvs = [
      for (final (s1, s2) in _restLimbs.values)
        if (s1.n >= _minRestSamples) (s1.cv + s2.cv) / 2,
    ];
    if (cvs.isEmpty) return false;
    return (spec.sides == 'best' ? cvs.reduce(math.min) : cvs.reduce(math.max)) > _maxRestLimbCv;
  }

  /// When the angle crossed the rest-zone edge, interpolated between the previous frame and
  /// this one. Rep durations then do not depend on where frames happen to fall: at 7 fps the
  /// frame grid alone would shift a rep's measured length by up to 140 ms.
  int _crossingMs(int tMs, double v) {
    final pv = _prevV, pt = _prevMs;
    if (pv == null || pt == null || tMs <= pt || v == pv) return tMs;
    final f = ((spec.rest.threshold - pv) / (v - pv)).clamp(0.0, 1.0);
    return pt + ((tMs - pt) * f).round();
  }

  void _startRep(int tMs, double v) {
    _phase = RepPhase.moving;
    _repStartMs = tMs;
    _reachedPeak = false;
    _peakValue = v;
    _repFrames = 0;
    _repInvisible = 0;
    _repFormBreaks = 0;
    _repWrongPosition = 0;
    _repGlitches = 0;
    _peakSpreads.clear();
    _bone1.reset();
    _bone2.reset();
  }

  void _accumulate(PoseFrame f, double v) {
    _repFrames++;
    final towardPeak = spec.peak.below != null ? v < _peakValue : v > _peakValue;
    if (towardPeak) _peakValue = v;
    final atPeak = spec.peak.contains(v);
    if (atPeak) _reachedPeak = true;

    final side = _side ?? 'left';
    if (!_positionOk(f)) _repWrongPosition++;
    for (final rule in spec.form) {
      if (rule.type == 'orientation') continue;
      if (rule.type == 'ankle_spread') {
        final spread = atPeak ? _ankleSpread(f) : null;
        if (spread != null) _peakSpreads.add(spread);
      } else {
        final a = f.get(side, rule.joints[0]), b = f.get(side, rule.joints[1]), c = f.get(side, rule.joints[2]);
        if (a != null && b != null && c != null && angleDeg(a, b, c) < rule.min) _repFormBreaks++;
      }
    }

    final torso = _torso(f, side);
    final a = f.get(side, spec.joints[0]), b = f.get(side, spec.joints[1]), c = f.get(side, spec.joints[2]);
    if (torso != null && a != null && b != null && c != null && spec.sides == 'best') {
      _bone1.add(a.distanceTo(b) / torso);
      _bone2.add(b.distanceTo(c) / torso);
    }
    _hint = _reachedPeak ? 'Good. Come back up' : _towardPeakHint();
  }

  String _towardPeakHint() => switch (spec.key) {
        'pushup' || 'squat' || 'lunge' => 'Go lower',
        'jumping_jack' => 'Arms all the way up',
        'high_knees' => 'Knee higher',
        _ => 'Full range',
      };

  /// Every orientation rule holds (or cannot be judged because a joint is hidden).
  bool _positionOk(PoseFrame f) {
    final side = _side ?? 'left';
    for (final rule in spec.form) {
      if (rule.type != 'orientation') continue;
      final a = f.get(side, rule.joints[0]), b = f.get(side, rule.joints[1]);
      if (a == null || b == null) continue;
      final tilt = tiltFromHorizontalDeg(a, b);
      final off = rule.axis == 'horizontal' ? tilt : 90 - tilt;
      if (off > rule.maxDeg) return false;
    }
    return true;
  }

  /// Ankle distance in torso lengths (shoulder midpoint to hip midpoint). The torso is the
  /// longest, steadiest segment a front camera sees; hip width is short and jitters.
  double? _ankleSpread(PoseFrame f) {
    final la = f.get('left', 'ankle'), ra = f.get('right', 'ankle');
    final ls = f.get('left', 'shoulder'), rs = f.get('right', 'shoulder');
    final lh = f.get('left', 'hip'), rh = f.get('right', 'hip');
    if (la == null || ra == null || ls == null || rs == null || lh == null || rh == null) return null;
    final torso = Landmark((ls.x + rs.x) / 2, (ls.y + rs.y) / 2, 1).distanceTo(Landmark((lh.x + rh.x) / 2, (lh.y + rh.y) / 2, 1));
    return torso > 0 ? la.distanceTo(ra) / torso : null;
  }

  /// Median, so one noisy frame at the top of a rep can neither pass nor fail it.
  static double _median(List<double> xs) {
    if (xs.isEmpty) return 0;
    final s = [...xs]..sort();
    final m = s.length ~/ 2;
    return s.length.isOdd ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  RepResult? _finishRep(int tMs) {
    final durationS = (tMs - _repStartMs) / 1000.0;
    if (!_reachedPeak) {
      // Movement that never got halfway to the peak is noise, not an attempt.
      final halfway = (spec.rest.threshold + spec.peak.threshold) / 2;
      final pastHalf = spec.peak.below != null ? _peakValue < halfway : _peakValue > halfway;
      if (!pastHalf) return null;
      _hint = _towardPeakHint();
      return _record(tMs, false, 'partial_range');
    }
    String? reason;
    if (_unsteady) {
      reason = 'unsteady_tracking';
    } else if (_repFrames > 0 && _repInvisible / _repFrames > _maxInvisibleFraction) {
      reason = 'low_visibility';
    } else if (_repGlitches > 0 || (_bone1.n >= 3 && (_bone1.cv > _maxBoneCv || _bone2.cv > _maxBoneCv))) {
      reason = 'tracking_glitch';
    } else if (durationS < spec.minRepS) {
      reason = 'too_fast';
    } else if (durationS > spec.maxRepS) {
      reason = 'too_slow';
    } else if (_repFrames > 0 && _repWrongPosition / _repFrames > _maxFormBreakFraction) {
      reason = 'wrong_position';
    } else if (_formBroken()) {
      reason = 'form_break';
    }
    _hint = switch (reason) {
      null => 'Nice rep',
      'too_fast' => 'Slow down. Control every rep',
      'form_break' => spec.key == 'pushup' ? 'Keep your body in a straight line' : 'Watch your form',
      'low_visibility' || 'tracking_glitch' => 'Stay fully in view of the camera',
      'wrong_position' => 'Get into the position shown for this exercise',
      'unsteady_tracking' => 'Tracking is unsteady. Move closer or add light',
      _ => 'That rep did not count',
    };
    return _record(tMs, reason == null, reason);
  }

  bool _formBroken() {
    for (final rule in spec.form) {
      if (rule.type == 'ankle_spread') {
        if (_median(_peakSpreads) < rule.min) return true;
      }
    }
    final angleRules = spec.form.where((r) => r.type == 'angle').length;
    return angleRules > 0 && _repFrames > 0 && _repFormBreaks / (_repFrames * angleRules) > _maxFormBreakFraction;
  }

  RepResult _record(int tMs, bool valid, String? reason) {
    final rep = RepResult(
      index: _reps.length,
      startMs: _repStartMs - (_firstMs ?? 0),
      durationMs: tMs - _repStartMs,
      peakValue: double.parse(_peakValue.toStringAsFixed(1)),
      valid: valid,
      reason: reason,
    );
    _reps.add(rep);
    if (valid) _valid++;
    return rep;
  }

  // ── hold ─────────────────────────────────────────────────────────────

  void _hold(PoseFrame f, double v) {
    final inHold = spec.peak.contains(v) && _positionOk(f);
    if (spec.rest.contains(v)) _sawRest = true;
    if (inHold) {
      if (_phase != RepPhase.holding) {
        if (!_everHeld) _enteredWithoutRest = !_sawRest;
        _everHeld = true;
        _phase = RepPhase.holding;
      } else if (_holdLastInMs != null) {
        _holdMs += f.tMs - _holdLastInMs!;
      }
      _holdLastInMs = f.tMs;
      final side = _side ?? 'left';
      final hip = f.get(side, 'hip');
      final torso = _torso(f, side);
      if (hip != null && torso != null) {
        _holdHipX.add(hip.x / torso);
        _holdHipY.add(hip.y / torso);
      }
      _hint = 'Hold it. Body straight';
    } else {
      if (_phase == RepPhase.holding && _holdLastInMs != null && f.tMs - _holdLastInMs! > _holdGraceMs) {
        _closeHold(f.tMs);
      }
      if (_phase != RepPhase.holding) {
        _phase = _sawRest ? RepPhase.rest : RepPhase.waiting;
        _hint = _everHeld ? 'Straighten your body to keep the timer running' : 'Move into a plank';
      }
    }
  }

  void _closeHold(int tMs) {
    _phase = _sawRest ? RepPhase.rest : RepPhase.waiting;
    _holdLastInMs = null;
  }

  EngineUpdate _update(double? v, bool visible, RepResult? newRep) => EngineUpdate(
        validReps: _valid,
        attemptedReps: _reps.length,
        holdS: _holdMs / 1000.0,
        phase: _phase,
        metric: v,
        visible: visible,
        hint: _hint,
        newRep: newRep,
      );
}

/// Coefficient of variation of rep durations; matches `services.exercises.duration_cv`.
double durationCv(List<double> durations) {
  final values = durations.where((d) => d > 0).toList();
  if (values.length < 2) return 1.0;
  final mean = values.reduce((a, b) => a + b) / values.length;
  if (mean <= 0) return 1.0;
  final variance = values.fold(0.0, (s, d) => s + (d - mean) * (d - mean)) / values.length;
  return math.sqrt(variance) / mean;
}

/// Running mean and standard deviation (Welford), O(1) memory.
class _Stats {
  int n = 0;
  double _mean = 0;
  double _m2 = 0;

  void add(double x) {
    n++;
    final d = x - _mean;
    _mean += d / n;
    _m2 += d * (x - _mean);
  }

  void reset() {
    n = 0;
    _mean = 0;
    _m2 = 0;
  }

  double get std => n < 2 ? 0 : math.sqrt(_m2 / n);
  double get cv => _mean == 0 ? 0 : std / _mean;
}
