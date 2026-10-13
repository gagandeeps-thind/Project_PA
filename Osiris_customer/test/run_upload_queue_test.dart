import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:osiris_customer/services/run_upload_queue.dart';

/// A run persisted by an earlier app session, as it sits in SharedPreferences.
Map<String, Object> _saved({int? userId, DateTime? startedAt}) => {
      'osiris.active_run.v1': jsonEncode({
        'run_id': 42,
        'user_id': ?userId,
        'started_at': (startedAt ?? DateTime.now().toUtc()).toIso8601String(),
        'next_sequence': 2,
        'distance_m': 30.0,
        'pending': [
          {'sequence': 0, 't_ms': 0, 'lat': 44.6, 'lng': -63.6},
          {'sequence': 1, 't_ms': 5000, 'lat': 44.6001, 'lng': -63.6},
        ],
      }),
    };

Future<RunUploadQueue> _queue(Map<String, Object> prefs) async {
  SharedPreferences.setMockInitialValues(prefs);
  return RunUploadQueue(await SharedPreferences.getInstance());
}

void main() {
  test('a restored run is kept for the account that recorded it', () async {
    final q = await _queue(_saved(userId: 7));
    await q.bindUser(7);
    expect(q.active?.runId, 42);
    expect(q.active?.pending, hasLength(2));
  });

  test("another account never inherits someone else's unfinished run", () async {
    final q = await _queue(_saved(userId: 7));
    await q.bindUser(8);
    expect(q.active, isNull);
    // Discarded from storage too, so a restart does not bring it back.
    final prefs = await SharedPreferences.getInstance();
    expect(RunUploadQueue(prefs).active, isNull);
  });

  test('runs saved before runs had an owner are discarded on sign-in', () async {
    final q = await _queue(_saved(userId: null));
    await q.bindUser(7);
    expect(q.active, isNull);
  });

  test('signing out clears the saved run', () async {
    final q = await _queue(_saved(userId: 7));
    await q.bindUser(null);
    expect(q.active, isNull);
  });

  test('new runs record their owner and survive a restart', () async {
    final q = await _queue({});
    await q.begin(5, DateTime.now().toUtc(), userId: 7, challengeId: 3);
    final restored = RunUploadQueue(await SharedPreferences.getInstance());
    expect(restored.active?.userId, 7);
    expect(restored.active?.challengeId, 3);
  });

  test('a run left open for over 12 hours is stale', () async {
    final fresh = await _queue(_saved(userId: 7));
    expect(fresh.active!.isStale, isFalse);
    final old = await _queue(_saved(userId: 7, startedAt: DateTime.now().toUtc().subtract(const Duration(hours: 13))));
    expect(old.active!.isStale, isTrue);
  });
}
