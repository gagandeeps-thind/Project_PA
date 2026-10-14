// Course, challenge, attempt, and progression models for the R2 API (/api/v2).

import 'package:latlong2/latlong.dart';

/// The server sends naive UTC timestamps; mark them UTC before converting to local.
DateTime _date(dynamic v) {
  if (v == null) return DateTime.now();
  final s = v as String;
  final hasZone = s.endsWith('Z') || RegExp(r'[+-]\d\d:\d\d$').hasMatch(s);
  return DateTime.parse(hasZone ? s : '${s}Z').toLocal();
}

double _d(dynamic v) => (v as num?)?.toDouble() ?? 0.0;

List<LatLng> _route(dynamic v) => (v as List? ?? [])
    .map((p) => LatLng(_d((p as List)[0]), _d(p[1])))
    .toList();

/// Human-readable copy for server reason codes. Unknown codes fall back to the code.
const Map<String, String> reasonCopy = {
  'RUN_NOT_ACCEPTED': 'The run did not pass route verification.',
  'START_OUTSIDE_COURSE': 'The run never reached the course start.',
  'FINISH_OUTSIDE_COURSE': 'The run did not reach the course finish.',
  'DISTANCE_MISMATCH': 'The distance run on course differs too much from the course.',
  'ROUTE_OFF_COURSE': 'Too much of the run was off the course route.',
  'CLOCK_SKEW': 'Device timestamps did not match server time.',
  'REVIEW_REQUIRED': 'This result is exceptionally fast, so a reviewer will confirm it.',
  'REVIEW_REJECTED': 'A reviewer rejected this result.',
  'INSUFFICIENT_ROUTE_POINTS': 'Not enough GPS points were recorded.',
  'IMPOSSIBLE_SPEED': 'GPS showed a speed no runner can reach.',
  'ROUTE_GAP_TOO_LARGE': 'GPS dropped out for too long.',
  'DURATION_TOO_SHORT': 'The run was too short.',
  'DISTANCE_TOO_SHORT': 'The run covered too little distance.',
  'GPS_ACCURACY_TOO_LOW': 'GPS accuracy was too low.',
  'NON_MONOTONIC_TIMESTAMPS': 'GPS timestamps were out of order.',
};

String explainReason(String code) => reasonCopy[code] ?? code;

String formatDuration(double seconds) {
  final s = seconds.round();
  final h = s ~/ 3600;
  final m = (s % 3600) ~/ 60;
  final sec = s % 60;
  final mm = m.toString().padLeft(h > 0 ? 2 : 1, '0');
  final ss = sec.toString().padLeft(2, '0');
  return h > 0 ? '$h:$mm:$ss' : '$mm:$ss';
}

String formatDistance(double metres) =>
    metres >= 1000 ? '${(metres / 1000).toStringAsFixed(2)} km' : '${metres.round()} m';

class AttemptSummary {
  final int id;
  final int challengeId;
  final String status;
  final String? outcome;
  final int? runId;
  final double? elapsedSeconds;
  final double targetSeconds;
  final double? courseCoverage;
  final List<String> reasonCodes;
  final int xpAwarded;
  final DateTime joinedAt;

  const AttemptSummary({
    required this.id,
    required this.challengeId,
    required this.status,
    required this.outcome,
    required this.runId,
    required this.elapsedSeconds,
    required this.targetSeconds,
    required this.courseCoverage,
    required this.reasonCodes,
    required this.xpAwarded,
    required this.joinedAt,
  });

  factory AttemptSummary.fromJson(Map<String, dynamic> j) => AttemptSummary(
        id: j['id'] as int,
        challengeId: j['challenge_id'] as int,
        status: j['status'] as String,
        outcome: j['outcome'] as String?,
        runId: j['run_id'] as int?,
        elapsedSeconds: (j['elapsed_seconds'] as num?)?.toDouble(),
        targetSeconds: _d(j['target_seconds']),
        courseCoverage: (j['course_coverage'] as num?)?.toDouble(),
        reasonCodes: (j['reason_codes'] as List? ?? []).cast<String>(),
        xpAwarded: j['xp_awarded'] as int? ?? 0,
        joinedAt: _date(j['joined_at']),
      );

  /// Short status label for chips and lists.
  String get label {
    if (outcome == 'won') return 'Won';
    if (outcome == 'lost') return 'Completed';
    if (outcome == 'voided') return 'Voided';
    switch (status) {
      case 'joined':
        return 'Joined';
      case 'review_required':
        return 'In review';
      case 'rejected':
        return 'Not counted';
      default:
        return status;
    }
  }
}

class ChallengeSummary {
  final int id;
  final String title;
  final String status;
  final double courseDistanceM;
  final double targetSeconds;
  final int entryCrystals;
  final String rewardPolicy;
  final int winXp;
  final int participationXp;
  final String? safetyNotes;
  final DateTime closesAt;
  final LatLng marker;
  final double? distanceKm;
  final int attemptCount;
  final bool isMine;
  final AttemptSummary? myAttempt;
  final String termsHash;

  const ChallengeSummary({
    required this.id,
    required this.title,
    required this.status,
    required this.courseDistanceM,
    required this.targetSeconds,
    required this.entryCrystals,
    required this.rewardPolicy,
    required this.winXp,
    required this.participationXp,
    required this.safetyNotes,
    required this.closesAt,
    required this.marker,
    required this.distanceKm,
    required this.attemptCount,
    required this.isMine,
    required this.myAttempt,
    required this.termsHash,
  });

  factory ChallengeSummary.fromJson(Map<String, dynamic> j) => ChallengeSummary(
        id: j['id'] as int,
        title: j['title'] as String,
        status: j['status'] as String,
        courseDistanceM: _d(j['course_distance_m']),
        targetSeconds: _d(j['target_seconds']),
        entryCrystals: j['entry_crystals'] as int? ?? 0,
        rewardPolicy: j['reward_policy'] as String? ?? 'xp_badge',
        winXp: j['win_xp'] as int? ?? 0,
        participationXp: j['participation_xp'] as int? ?? 0,
        safetyNotes: j['safety_notes'] as String?,
        closesAt: _date(j['closes_at']),
        marker: LatLng(_d(j['marker_lat']), _d(j['marker_lng'])),
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        attemptCount: j['attempt_count'] as int? ?? 0,
        isMine: j['is_mine'] as bool? ?? false,
        myAttempt: j['my_attempt'] == null
            ? null
            : AttemptSummary.fromJson(j['my_attempt'] as Map<String, dynamic>),
        termsHash: j['terms_hash'] as String? ?? '',
      );

  String get closesIn {
    final d = closesAt.difference(DateTime.now());
    if (d.isNegative) return 'closed';
    if (d.inDays >= 1) return '${d.inDays}d ${d.inHours % 24}h left';
    if (d.inHours >= 1) return '${d.inHours}h ${d.inMinutes % 60}m left';
    return '${d.inMinutes}m left';
  }
}

class CourseSummary {
  final int id;
  final String name;
  final String status;
  final double distanceM;
  final double benchmarkSeconds;
  final bool isLoop;
  final List<LatLng> route;
  final int? openChallengeId;

  const CourseSummary({
    required this.id,
    required this.name,
    required this.status,
    required this.distanceM,
    required this.benchmarkSeconds,
    required this.isLoop,
    required this.route,
    required this.openChallengeId,
  });

  factory CourseSummary.fromJson(Map<String, dynamic> j) => CourseSummary(
        id: j['id'] as int,
        name: j['name'] as String,
        status: j['status'] as String,
        distanceM: _d(j['distance_m']),
        benchmarkSeconds: _d(j['benchmark_seconds']),
        isLoop: j['is_loop'] as bool? ?? false,
        route: _route(j['route']),
        openChallengeId: j['open_challenge_id'] as int?,
      );
}

class CourseRoute {
  final List<LatLng> route;
  final double startRadiusM;

  const CourseRoute({required this.route, required this.startRadiusM});

  factory CourseRoute.fromJson(Map<String, dynamic> j) => CourseRoute(
        route: _route(j['route']),
        startRadiusM: _d(j['start_radius_m']),
      );
}

class Badge {
  final String code;
  final String label;

  const Badge({required this.code, required this.label});

  factory Badge.fromJson(Map<String, dynamic> j) =>
      Badge(code: j['code'] as String, label: j['label'] as String? ?? j['code'] as String);
}

class Progression {
  final int xp;
  final String performanceRank;
  final int? nextRankXp;
  final int verifiedRuns;
  final int courses;
  final int challengesWon;
  final int defenses;
  final List<Badge> badges;

  const Progression({
    required this.xp,
    required this.performanceRank,
    required this.nextRankXp,
    required this.verifiedRuns,
    required this.courses,
    required this.challengesWon,
    required this.defenses,
    required this.badges,
  });

  factory Progression.fromJson(Map<String, dynamic> j) => Progression(
        xp: j['xp'] as int? ?? 0,
        performanceRank: j['performance_rank'] as String? ?? 'Bronze',
        nextRankXp: j['next_rank_xp'] as int?,
        verifiedRuns: j['verified_runs'] as int? ?? 0,
        courses: j['courses'] as int? ?? 0,
        challengesWon: j['challenges_won'] as int? ?? 0,
        defenses: j['defenses'] as int? ?? 0,
        badges: (j['badges'] as List? ?? [])
            .map((b) => Badge.fromJson(b as Map<String, dynamic>))
            .toList(),
      );
}
