import 'package:dio/dio.dart';

import 'exercise_store.dart';

/// Result of one upload pass.
class SyncResult {
  final int uploaded;
  final int xpAwarded;
  final bool offline;

  const SyncResult(this.uploaded, this.xpAwarded, {this.offline = false});
}

/// Uploads saved sets in the order they were recorded. Each upload is idempotent on the
/// server (`client_session_id`), so a response lost in transit is safe to retry.
class ExerciseSync {
  final ExerciseStore store;
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> body) submit;
  final Future<Map<String, dynamic>> Function()? fetchHistory;
  bool _running = false;

  ExerciseSync(this.store, this.submit, {this.fetchHistory});

  /// Pulls the server's current status for recent sets, so a flagged set that an admin later
  /// approved or rejected shows the outcome. Returns how many local sets changed; 0 offline.
  Future<int> refreshOutcomes() async {
    final fetch = fetchHistory;
    if (fetch == null) return 0;
    try {
      final sessions = (await fetch())['sessions'] as List;
      return store.applyServerResults([
        for (final raw in sessions)
          if (raw is Map<String, dynamic>)
            (
              id: raw['client_session_id'] as String,
              status: raw['status'] as String,
              xp: (raw['xp_awarded'] as num).toInt(),
            ),
      ]);
    } on DioException {
      return 0;
    }
  }

  Future<SyncResult> flush(int userId) async {
    if (_running) return const SyncResult(0, 0);
    _running = true;
    var uploaded = 0, xp = 0;
    try {
      for (final s in await store.pending(userId)) {
        try {
          final out = await submit(s.toUpload());
          final awarded = (out['xp_awarded'] as num?)?.toInt() ?? 0;
          await store.markSynced(s.id, serverStatus: out['status'] as String, xpAwarded: awarded);
          uploaded++;
          xp += awarded;
        } on DioException catch (e) {
          final code = e.response?.statusCode;
          if (code == null || code >= 500 || code == 429 || code == 401) {
            // Offline, server trouble or an expired session: keep it for the next pass.
            await store.markFailed(s.id, e.message ?? 'network', permanent: false);
            return SyncResult(uploaded, xp, offline: code == null);
          }
          // 4xx: the server will never accept this body; stop retrying it.
          await store.markFailed(s.id, 'HTTP $code', permanent: true);
        }
      }
      return SyncResult(uploaded, xp);
    } finally {
      _running = false;
    }
  }
}
