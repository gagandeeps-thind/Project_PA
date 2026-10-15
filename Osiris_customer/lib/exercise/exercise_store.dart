import 'dart:convert';
import 'dart:math' as math;

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'rep_engine.dart';

/// A set saved on the phone, waiting to upload or already accepted by the server.
class StoredSession {
  final String id;
  final int userId;
  final String exerciseKey;
  final String rulesVersion;
  final DateTime startedAt;
  final double durationS;
  final int repsAttempted;
  final int repsValid;
  final double holdS;
  final double formScore;
  final String verdict;
  final List<String> reasons;
  final List<double> repDurationsS;
  final String syncState; // pending | synced | failed
  final String? serverStatus;
  final int xpAwarded;

  const StoredSession({
    required this.id,
    required this.userId,
    required this.exerciseKey,
    required this.rulesVersion,
    required this.startedAt,
    required this.durationS,
    required this.repsAttempted,
    required this.repsValid,
    required this.holdS,
    required this.formScore,
    required this.verdict,
    required this.reasons,
    required this.repDurationsS,
    required this.syncState,
    this.serverStatus,
    this.xpAwarded = 0,
  });

  /// Body for `POST /api/v2/exercise-sessions`.
  Map<String, dynamic> toUpload() => {
        'client_session_id': id,
        'exercise_key': exerciseKey,
        'rules_version': rulesVersion,
        'started_at': startedAt.toUtc().toIso8601String(),
        'duration_s': durationS,
        'reps_attempted': repsAttempted,
        'reps_valid': repsValid,
        'hold_s': holdS,
        'form_score': formScore,
        'client_verdict': verdict,
        'reason_codes': reasons,
        'rep_durations_s': repDurationsS,
      };
}

/// Local SQLite store for the exercise feature, so counting, history and personal bests
/// work offline and instantly. Camera frames and landmarks are never stored; only the
/// per-set summary and per-rep timings.
class ExerciseStore {
  static const fileName = 'osiris_exercise.db';
  static const _version = 1;

  final Database db;

  ExerciseStore._(this.db);

  static Future<ExerciseStore> open({DatabaseFactory? factory, String? path}) async {
    final f = factory ?? databaseFactory;
    final dbPath = path ?? p.join(await f.getDatabasesPath(), fileName);
    final db = await f.openDatabase(dbPath,
        options: OpenDatabaseOptions(
          version: _version,
          onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
          onCreate: (db, _) => _create(db),
        ));
    return ExerciseStore._(db);
  }

  static Future<void> _create(Database db) async {
    final batch = db.batch()
      ..execute('''
        CREATE TABLE exercise_catalog (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          rules_version TEXT NOT NULL,
          json TEXT NOT NULL,
          fetched_at INTEGER NOT NULL
        )''')
      ..execute('''
        CREATE TABLE exercise_sessions (
          id TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL,
          exercise_key TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          started_at INTEGER NOT NULL,
          duration_s REAL NOT NULL,
          reps_attempted INTEGER NOT NULL,
          reps_valid INTEGER NOT NULL,
          hold_s REAL NOT NULL,
          form_score REAL NOT NULL,
          verdict TEXT NOT NULL,
          reasons_json TEXT NOT NULL,
          sync_state TEXT NOT NULL DEFAULT 'pending',
          server_status TEXT,
          xp_awarded INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at INTEGER NOT NULL
        )''')
      ..execute('CREATE INDEX ix_exercise_sessions_sync ON exercise_sessions (sync_state, created_at)')
      ..execute('CREATE INDEX ix_exercise_sessions_user ON exercise_sessions (user_id, exercise_key, started_at)')
      ..execute('''
        CREATE TABLE exercise_reps (
          session_id TEXT NOT NULL REFERENCES exercise_sessions (id) ON DELETE CASCADE,
          idx INTEGER NOT NULL,
          start_ms INTEGER NOT NULL,
          duration_ms INTEGER NOT NULL,
          peak_value REAL NOT NULL,
          valid INTEGER NOT NULL,
          reason TEXT,
          PRIMARY KEY (session_id, idx)
        )''');
    await batch.commit(noResult: true);
  }

  Future<void> close() => db.close();

  // ── catalog cache ────────────────────────────────────────────────────

  Future<String?> cachedCatalogJson() async {
    final rows = await db.query('exercise_catalog', columns: ['json'], where: 'id = 1');
    return rows.isEmpty ? null : rows.first['json'] as String;
  }

  Future<void> cacheCatalog(String rulesVersion, String json) => db.insert(
        'exercise_catalog',
        {'id': 1, 'rules_version': rulesVersion, 'json': json, 'fetched_at': DateTime.now().millisecondsSinceEpoch},
        conflictAlgorithm: ConflictAlgorithm.replace,
      );

  // ── sessions ─────────────────────────────────────────────────────────

  /// Random 128-bit id, used as the upload's idempotency key.
  static String newSessionId() {
    final r = math.Random.secure();
    return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }

  Future<String> saveSession(SessionSummary s, {required int userId, required DateTime startedAt, String? id}) async {
    final sessionId = id ?? newSessionId();
    await db.transaction((txn) async {
      await txn.insert('exercise_sessions', {
        'id': sessionId,
        'user_id': userId,
        'exercise_key': s.exerciseKey,
        'rules_version': s.rulesVersion,
        'started_at': startedAt.millisecondsSinceEpoch,
        'duration_s': s.durationS,
        'reps_attempted': s.repsAttempted,
        'reps_valid': s.repsValid,
        'hold_s': s.holdS,
        'form_score': s.formScore,
        'verdict': s.verdict,
        'reasons_json': jsonEncode(s.reasons),
        'created_at': DateTime.now().millisecondsSinceEpoch,
      });
      final batch = txn.batch();
      for (final r in s.reps) {
        batch.insert('exercise_reps', {
          'session_id': sessionId,
          'idx': r.index,
          'start_ms': r.startMs,
          'duration_ms': r.durationMs,
          'peak_value': r.peakValue,
          'valid': r.valid ? 1 : 0,
          'reason': r.reason,
        });
      }
      await batch.commit(noResult: true);
    });
    return sessionId;
  }

  Future<List<StoredSession>> pending(int userId) => _sessions('user_id = ? AND sync_state = ?', [userId, 'pending'],
      orderBy: 'created_at ASC');

  Future<List<StoredSession>> recent(int userId, {int limit = 20}) =>
      _sessions('user_id = ?', [userId], orderBy: 'started_at DESC', limit: limit);

  Future<void> markSynced(String id, {required String serverStatus, required int xpAwarded}) => db.update(
        'exercise_sessions',
        {'sync_state': 'synced', 'server_status': serverStatus, 'xp_awarded': xpAwarded, 'last_error': null},
        where: 'id = ?',
        whereArgs: [id],
      );

  /// A permanent refusal (e.g. 422) stops retries; a transient one only counts the attempt.
  Future<void> markFailed(String id, String error, {required bool permanent}) => db.rawUpdate(
        'UPDATE exercise_sessions SET attempts = attempts + 1, last_error = ?, sync_state = ? WHERE id = ?',
        [error, permanent ? 'failed' : 'pending', id],
      );

  /// Best verified set per exercise for this player: most valid reps, or longest hold.
  Future<Map<String, double>> personalBests(int userId) async {
    final rows = await db.rawQuery('''
      SELECT exercise_key, MAX(CASE WHEN hold_s > 0 THEN hold_s ELSE reps_valid END) AS best
      FROM exercise_sessions
      WHERE user_id = ? AND verdict = 'verified' AND COALESCE(server_status, 'verified') = 'verified'
      GROUP BY exercise_key''', [userId]);
    return {for (final r in rows) r['exercise_key'] as String: (r['best'] as num).toDouble()};
  }

  /// Erases one player's sets and reps from this phone (consent withdrawn with deletion).
  Future<int> deleteUserSessions(int userId) =>
      db.delete('exercise_sessions', where: 'user_id = ?', whereArgs: [userId]);

  /// Removes everything stored for other accounts, so one person's history never shows to
  /// the next person who signs in on this phone.
  Future<void> forgetOtherUsers(int? userId) =>
      db.delete('exercise_sessions', where: userId == null ? null : 'user_id != ?', whereArgs: userId == null ? null : [userId]);

  Future<List<StoredSession>> _sessions(String where, List<Object?> args, {String? orderBy, int? limit}) async {
    final rows = await db.query('exercise_sessions', where: where, whereArgs: args, orderBy: orderBy, limit: limit);
    if (rows.isEmpty) return const [];
    final ids = rows.map((r) => r['id'] as String).toList();
    final reps = await db.query('exercise_reps',
        columns: ['session_id', 'duration_ms'],
        where: 'valid = 1 AND session_id IN (${List.filled(ids.length, '?').join(',')})',
        whereArgs: ids,
        orderBy: 'session_id, idx');
    final durations = <String, List<double>>{};
    for (final r in reps) {
      durations.putIfAbsent(r['session_id'] as String, () => []).add((r['duration_ms'] as int) / 1000.0);
    }
    return [
      for (final r in rows)
        StoredSession(
          id: r['id'] as String,
          userId: r['user_id'] as int,
          exerciseKey: r['exercise_key'] as String,
          rulesVersion: r['rules_version'] as String,
          startedAt: DateTime.fromMillisecondsSinceEpoch(r['started_at'] as int),
          durationS: (r['duration_s'] as num).toDouble(),
          repsAttempted: r['reps_attempted'] as int,
          repsValid: r['reps_valid'] as int,
          holdS: (r['hold_s'] as num).toDouble(),
          formScore: (r['form_score'] as num).toDouble(),
          verdict: r['verdict'] as String,
          reasons: (jsonDecode(r['reasons_json'] as String) as List).cast<String>(),
          repDurationsS: durations[r['id']] ?? const [],
          syncState: r['sync_state'] as String,
          serverStatus: r['server_status'] as String?,
          xpAwarded: r['xp_awarded'] as int,
        ),
    ];
  }
}
