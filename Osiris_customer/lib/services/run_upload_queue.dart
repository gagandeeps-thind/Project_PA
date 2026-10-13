import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';

/// The run currently being recorded, persisted so an app restart or a network outage
/// never loses route points (PRD-003).
class ActiveRun {
  final int runId;
  /// The account that recorded the run. Null only for runs saved by older app versions.
  final int? userId;
  final DateTime startedAt;
  final int? challengeId;
  int nextSequence;
  double distanceM;
  final List<Map<String, dynamic>> pending;

  ActiveRun({
    required this.runId,
    this.userId,
    required this.startedAt,
    this.challengeId,
    this.nextSequence = 0,
    this.distanceM = 0,
    List<Map<String, dynamic>>? pending,
  }) : pending = pending ?? [];

  int get uploaded => nextSequence - pending.length;

  /// Runs left open this long were almost certainly abandoned (app killed, phone died).
  static const staleAfter = Duration(hours: 12);

  bool get isStale => DateTime.now().toUtc().difference(startedAt) > staleAfter;

  Map<String, dynamic> toJson() => {
        'run_id': runId,
        'user_id': userId,
        'started_at': startedAt.toIso8601String(),
        'challenge_id': challengeId,
        'next_sequence': nextSequence,
        'distance_m': distanceM,
        'pending': pending,
      };

  factory ActiveRun.fromJson(Map<String, dynamic> j) => ActiveRun(
        runId: j['run_id'] as int,
        userId: j['user_id'] as int?,
        startedAt: DateTime.parse(j['started_at'] as String),
        challengeId: j['challenge_id'] as int?,
        nextSequence: j['next_sequence'] as int? ?? 0,
        distanceM: (j['distance_m'] as num?)?.toDouble() ?? 0,
        pending: (j['pending'] as List? ?? [])
            .map((p) => Map<String, dynamic>.from(p as Map))
            .toList(),
      );
}

/// Durable, ordered upload queue for route points.
///
/// Points get contiguous sequence numbers at capture time and stay queued until the
/// server acknowledges them. If an upload's response is lost after the server stored it,
/// the next attempt gets a 409 sequence error; the queue then asks the server how many
/// points it holds and drops the ones already stored.
class RunUploadQueue {
  static const _key = 'osiris.active_run.v1';
  static const _batchSize = 400;

  final SharedPreferences _prefs;
  ActiveRun? _run;
  bool _flushing = false;

  RunUploadQueue(this._prefs) {
    final raw = _prefs.getString(_key);
    if (raw != null) {
      try {
        _run = ActiveRun.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      } catch (_) {
        _prefs.remove(_key);
      }
    }
  }

  ActiveRun? get active => _run;

  /// Call whenever the signed-in account changes (sign in, sign up, session restore, sign
  /// out with null). A saved run that belongs to anyone else is discarded, so one person's
  /// unsent GPS points are never shown to, or uploaded by, the next person on this phone.
  Future<void> bindUser(int? userId) async {
    final run = _run;
    if (run != null && (userId == null || run.userId != userId)) await clear();
  }

  Future<void> begin(int runId, DateTime startedAt, {required int userId, int? challengeId}) async {
    _run = ActiveRun(runId: runId, userId: userId, startedAt: startedAt, challengeId: challengeId);
    await _save();
  }

  Future<void> add(Map<String, dynamic> point, double segmentM) async {
    final run = _run;
    if (run == null) return;
    run.pending.add({...point, 'sequence': run.nextSequence++});
    run.distanceM += segmentM;
    await _save();
  }

  /// Upload everything queued. Returns true when the queue is empty afterwards. Network
  /// failures leave points queued for the next call; other errors are rethrown.
  Future<bool> flush(ApiClient api) async {
    final run = _run;
    if (run == null) return true;
    if (_flushing) return run.pending.isEmpty;
    _flushing = true;
    try {
      while (run.pending.isNotEmpty) {
        final batch = run.pending.take(_batchSize).toList();
        try {
          await api.appendRunPoints(run.runId, batch);
          run.pending.removeRange(0, batch.length);
        } on DioException catch (e) {
          if (e.response?.statusCode == 409) {
            final stored = (await api.getRun(run.runId))['point_count'] as int? ?? 0;
            final before = run.pending.length;
            run.pending.removeWhere((p) => (p['sequence'] as int) < stored);
            if (run.pending.length == before) rethrow;
          } else if (e.response == null) {
            return false; // offline; keep for later
          } else {
            rethrow;
          }
        } finally {
          await _save();
        }
      }
      return true;
    } finally {
      _flushing = false;
    }
  }

  Future<void> clear() async {
    _run = null;
    await _prefs.remove(_key);
  }

  Future<void> _save() async {
    final run = _run;
    if (run == null) return;
    await _prefs.setString(_key, jsonEncode(run.toJson()));
  }
}
