import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/catalog_repository.dart';
import 'package:osiris_customer/exercise/exercise_store.dart';
import 'package:osiris_customer/exercise/exercise_sync.dart';
import 'package:osiris_customer/exercise/rep_engine.dart';
import 'package:osiris_customer/providers.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

SessionSummary _summary({int valid = 10, String verdict = 'verified', String key = 'pushup', double hold = 0}) =>
    SessionSummary(
      exerciseKey: key,
      rulesVersion: 'exercise-rules-v1',
      durationS: 30,
      repsAttempted: valid + 1,
      repsValid: valid,
      holdS: hold,
      formScore: 0.9,
      verdict: verdict,
      reasons: const ['too_fast'],
      reps: [
        for (var i = 0; i <= valid; i++)
          RepResult(
              index: i,
              startMs: i * 2000,
              durationMs: 1500 + i * 10,
              peakValue: 80,
              valid: i < valid,
              reason: i < valid ? null : 'too_fast'),
      ],
    );

DioException _dioError(int? status) => DioException(
      requestOptions: RequestOptions(path: '/api/v2/exercise-sessions'),
      response: status == null ? null : Response(requestOptions: RequestOptions(), statusCode: status),
      type: status == null ? DioExceptionType.connectionError : DioExceptionType.badResponse,
    );

void main() {
  sqfliteFfiInit();
  late ExerciseStore store;

  setUp(() async {
    store = await ExerciseStore.open(factory: databaseFactoryFfi, path: inMemoryDatabasePath);
  });
  tearDown(() => store.close());

  test('a saved set round-trips with its valid rep timings', () async {
    final started = DateTime.utc(2026, 10, 14, 7, 30);
    final id = await store.saveSession(_summary(valid: 3), userId: 7, startedAt: started);
    final pending = await store.pending(7);
    expect(pending, hasLength(1));
    final s = pending.single;
    expect(s.id, id);
    expect(s.repDurationsS, [1.5, 1.51, 1.52]);
    final body = s.toUpload();
    expect(body['client_session_id'], id);
    expect(body['reps_valid'], 3);
    expect(body['started_at'], '2026-10-14T07:30:00.000Z');
    expect(body['reason_codes'], ['too_fast']);
    expect(id, matches(RegExp(r'^[0-9a-f]{32}$')));
  });

  test('sync uploads in order, records XP, and never re-sends a synced set', () async {
    await store.saveSession(_summary(valid: 5), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    await store.saveSession(_summary(valid: 8), userId: 7, startedAt: DateTime.utc(2026, 1, 2));
    final sent = <int>[];
    final sync = ExerciseSync(store, (body) async {
      sent.add(body['reps_valid'] as int);
      return {'status': 'verified', 'xp_awarded': body['reps_valid']};
    });
    final r = await sync.flush(7);
    expect(r.uploaded, 2);
    expect(r.xpAwarded, 13);
    expect(sent, [5, 8]);
    expect(await store.pending(7), isEmpty);
    expect((await sync.flush(7)).uploaded, 0);
    expect(sent, hasLength(2));
  });

  test('offline keeps the set for later; a 422 stops retrying it', () async {
    await store.saveSession(_summary(), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    var offline = await ExerciseSync(store, (_) async => throw _dioError(null)).flush(7);
    expect(offline.offline, isTrue);
    expect(await store.pending(7), hasLength(1));
    offline = await ExerciseSync(store, (_) async => throw _dioError(503)).flush(7);
    expect(await store.pending(7), hasLength(1));
    await ExerciseSync(store, (_) async => throw _dioError(422)).flush(7);
    expect(await store.pending(7), isEmpty);
    expect((await store.recent(7)).single.syncState, 'failed');
  });

  test('personal bests count only verified sets, per exercise', () async {
    await store.saveSession(_summary(valid: 12), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    await store.saveSession(_summary(valid: 30, verdict: 'review'), userId: 7, startedAt: DateTime.utc(2026, 1, 2));
    await store.saveSession(_summary(valid: 0, key: 'plank', hold: 42.5), userId: 7, startedAt: DateTime.utc(2026, 1, 3));
    await store.saveSession(_summary(valid: 50), userId: 8, startedAt: DateTime.utc(2026, 1, 3));
    expect(await store.personalBests(7), {'pushup': 12.0, 'plank': 42.5});
  });

  test("another account's sets are forgotten on sign-in, with their reps", () async {
    await store.saveSession(_summary(), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    await store.saveSession(_summary(), userId: 8, startedAt: DateTime.utc(2026, 1, 1));
    await store.forgetOtherUsers(8);
    expect(await store.recent(7), isEmpty);
    expect(await store.recent(8), hasLength(1));
    final orphanReps = await store.db.rawQuery(
        'SELECT COUNT(*) AS n FROM exercise_reps WHERE session_id NOT IN (SELECT id FROM exercise_sessions)');
    expect(orphanReps.single['n'], 0);
  });

  test("deleting a player's sets removes their reps and nobody else's", () async {
    await store.saveSession(_summary(), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    await store.saveSession(_summary(), userId: 8, startedAt: DateTime.utc(2026, 1, 1));
    expect(await store.deleteUserSessions(7), 1);
    expect(await store.recent(7), isEmpty);
    expect(await store.recent(8), hasLength(1));
    final reps = await store.db.rawQuery('SELECT COUNT(*) AS n FROM exercise_reps');
    expect(reps.single['n'], 11, reason: "only user 8's 11 reps remain");
  });

  test('review outcomes reach sets already uploaded, and only those', () async {
    final a = await store.saveSession(_summary(valid: 10), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    final b = await store.saveSession(_summary(valid: 9), userId: 7, startedAt: DateTime.utc(2026, 1, 2));
    await ExerciseSync(store, (body) async => {'status': 'review', 'xp_awarded': 0}).flush(7);
    final c = await store.saveSession(_summary(valid: 8), userId: 7, startedAt: DateTime.utc(2026, 1, 3));
    final sync = ExerciseSync(store, (_) async => throw _dioError(null), fetchHistory: () async => {
          'sessions': [
            {'client_session_id': a, 'status': 'verified', 'xp_awarded': 10},
            {'client_session_id': b, 'status': 'review', 'xp_awarded': 0},
            {'client_session_id': c, 'status': 'verified', 'xp_awarded': 99},
          ],
        });
    expect(await sync.refreshOutcomes(), 1, reason: 'a changed; b is unchanged; c was never uploaded');
    final byId = {for (final s in await store.recent(7)) s.id: s};
    expect(byId[a]!.serverStatus, 'verified');
    expect(byId[a]!.xpAwarded, 10);
    expect(byId[c]!.syncState, 'pending');
    expect(byId[c]!.xpAwarded, 0);
    expect(await store.personalBests(7), {'pushup': 10.0}, reason: 'the approved set now counts as a best');
    final offline = ExerciseSync(store, (_) async => {}, fetchHistory: () async => throw _dioError(null));
    expect(await offline.refreshOutcomes(), 0);
  });

  test('the database is opened only when the signed-in account changes', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    var opens = 0;
    Future<ExerciseStore> open() async {
      opens++;
      return store;
    }

    await store.saveSession(_summary(), userId: 7, startedAt: DateTime.utc(2026, 1, 1));
    await bindExerciseOwner(prefs, 7, open); // first sign-in: owner unknown, so check once
    await bindExerciseOwner(prefs, 7, open); // every later launch as the same account: free
    await bindExerciseOwner(prefs, 7, open);
    expect(opens, 1);
    expect(await store.recent(7), hasLength(1));

    await bindExerciseOwner(prefs, 8, open); // another account signs in: 7's sets go
    expect(opens, 2);
    expect(await store.recent(7), isEmpty);

    await bindExerciseOwner(prefs, null, open); // sign-out clears everything
    expect(opens, 3);
    await bindExerciseOwner(prefs, 8, open); // owner forgotten, so the next sign-in checks again
    expect(opens, 4);
  });

  test('catalog: bundled first, then the cached server copy', () async {
    final bundled = File('assets/exercise_catalog.json').readAsStringSync();
    final serverCopy = jsonDecode(bundled) as Map<String, dynamic>;
    serverCopy['rules_version'] = 'exercise-rules-v2';
    final repo = CatalogRepository(store: store, loadBundled: () async => bundled, fetch: () async => serverCopy);
    expect((await repo.load()).rulesVersion, 'exercise-rules-v1');
    expect((await repo.refresh())?.rulesVersion, 'exercise-rules-v2');
    expect((await repo.load()).rulesVersion, 'exercise-rules-v2');
    final offline = CatalogRepository(store: store, loadBundled: () async => bundled, fetch: () async => throw _dioError(null));
    expect(await offline.refresh(), isNull);
    expect((await offline.load()).rulesVersion, 'exercise-rules-v2');
  });

  test('saving 20 sets and reading history stays fast', () async {
    final sw = Stopwatch()..start();
    for (var i = 0; i < 20; i++) {
      await store.saveSession(_summary(valid: 25), userId: 7, startedAt: DateTime.utc(2026, 1, 1, 0, i));
    }
    final saveMs = sw.elapsedMilliseconds;
    sw.reset();
    final recent = await store.recent(7, limit: 20);
    final bests = await store.personalBests(7);
    expect(recent, hasLength(20));
    expect(bests['pushup'], 25);
    expect(saveMs, lessThan(2000), reason: '20 sets with 520 reps took $saveMs ms');
    expect(sw.elapsedMilliseconds, lessThan(500), reason: 'history read took ${sw.elapsedMilliseconds} ms');
  });
}
