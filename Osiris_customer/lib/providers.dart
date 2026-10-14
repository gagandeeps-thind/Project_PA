import 'dart:async';

import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api_client.dart';
import 'api/challenge_models.dart';
import 'api/growth_models.dart';
import 'api/models.dart';
import 'exercise/catalog_repository.dart';
import 'exercise/exercise_catalog.dart';
import 'exercise/exercise_store.dart';
import 'exercise/exercise_sync.dart';
import 'exercise/mlkit_pose_source.dart';
import 'exercise/pose_source.dart';
import 'exercise/rep_engine.dart';
import 'services/run_upload_queue.dart';

// ── SharedPreferences (overridden in main) ─────────────────────────────

final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) => throw UnimplementedError(
    'sharedPreferencesProvider must be overridden in ProviderScope',
  ),
);

// ── Secure Storage ─────────────────────────────────────────────────────

final secureStorageProvider = Provider<FlutterSecureStorage>(
  (ref) => const FlutterSecureStorage(),
);

// ── API Client (singleton) ─────────────────────────────────────────────

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

// ── Feature flags ──────────────────────────────────────────────────────

/// Legacy bounty/vault/domain screens stay reachable only behind this flag while the
/// product migrates to the run → course → challenge loop (Backlog Phase 3).
const bool kLegacyFeatures = bool.fromEnvironment('OSIRIS_LEGACY_FEATURES');

// ── Run upload queue (durable across restarts) ─────────────────────────

final runQueueProvider = Provider<RunUploadQueue>(
  (ref) => RunUploadQueue(ref.read(sharedPreferencesProvider)),
);

// ── Progression ─────────────────────────────────────────────────────────

final progressionProvider = FutureProvider.autoDispose<Progression>((ref) async {
  final data = await ref.read(apiClientProvider).getProgression();
  return Progression.fromJson(data);
});

// ── Growth: install id, today, profile ─────────────────────────────────

/// Random per-install id for anonymous funnel events (install, first open). Not tied to
/// the device hardware and cleared if the app is reinstalled.
final installIdProvider = Provider<String>((ref) {
  final prefs = ref.read(sharedPreferencesProvider);
  var id = prefs.getString('install_id');
  if (id == null) {
    final now = DateTime.now().microsecondsSinceEpoch;
    id = 'i-${now.toRadixString(36)}-${(now * 7919 % 1000003).toRadixString(36)}';
    prefs.setString('install_id', id);
    ref.read(apiClientProvider).trackEvent('app_installed', installId: id);
  }
  return id;
});

int localUtcOffsetMinutes() => DateTime.now().timeZoneOffset.inMinutes;

/// Home screen data. Includes a starter challenge once a position is known.
final todayProvider = FutureProvider.autoDispose<TodayData>((ref) async {
  final pos = ref.watch(lastKnownPositionProvider);
  final data = await ref.read(apiClientProvider).getToday(
        lat: pos?.$1,
        lng: pos?.$2,
        utcOffsetMinutes: localUtcOffsetMinutes(),
      );
  return TodayData.fromJson(data);
});

/// Last known position, used only to suggest one nearby starter challenge. Never stored.
final lastKnownPositionProvider =
    NotifierProvider<LastPositionNotifier, (double, double)?>(LastPositionNotifier.new);

class LastPositionNotifier extends Notifier<(double, double)?> {
  @override
  (double, double)? build() => null;

  void set(double lat, double lng) => state = (lat, lng);
}

final myProfileV2Provider = FutureProvider.autoDispose<PlayerProfileV2>((ref) async {
  return PlayerProfileV2.fromJson(await ref.read(apiClientProvider).getMyProfile());
});

// ── Auth State ─────────────────────────────────────────────────────────

final authProvider =
    NotifierProvider<AuthNotifier, UserProfile?>(() => AuthNotifier());

/// Manages authentication state: login, register, logout, session restore.
class AuthNotifier extends Notifier<UserProfile?> {
  @override
  UserProfile? build() {
    // Kick off async session restore (fire-and-forget).
    _loadSession();
    return null;
  }

  FlutterSecureStorage get _storage => ref.read(secureStorageProvider);
  ApiClient get _api => ref.read(apiClientProvider);

  // ── Session Restore ──────────────────────────────────────────────────

  Future<void> _loadSession() async {
    try {
      final token = await _storage.read(key: 'auth_token');
      final userIdStr = await _storage.read(key: 'user_id');

      if (token == null || userIdStr == null) return;

      _api.setToken(token);
      final userId = int.parse(userIdStr);
      final data = await _api.getUserProfile(userId);
      final profile = UserProfile.fromJson(data);

      // Only restore session for players
      if (profile.role != 'player') {
        await _clearCredentials();
        return;
      }

      await ref.read(runQueueProvider).bindUser(profile.id);
      _bindExerciseData(profile.id);
      state = profile;
    } catch (_) {
      // Silent fail — user will just see the login screen.
      await _clearCredentials();
    }
  }

  // ── Login ────────────────────────────────────────────────────────────

  /// Authenticate a player. Rejects non-player roles.
  Future<void> login(String email, String password) async {
    final timestamp = DateTime.now().toUtc().toIso8601String();
    final data = await _api.loginUser(email, password, timestamp);

    // *** CRITICAL: Reject non-player roles ***
    if (data['role'] != 'player') {
      throw Exception(
        'This app is for Osiris players only. '
        'Merchants and admins should use their dedicated apps.',
      );
    }

    final token = data['access_token'] as String;
    final userId = (data['id'] ?? data['user_id']) as int;

    _api.setToken(token);

    await _storage.write(key: 'auth_token', value: token);
    await _storage.write(key: 'user_id', value: userId.toString());

    // Fetch full profile
    final profileData = await _api.getUserProfile(userId);
    await ref.read(runQueueProvider).bindUser(userId);
    _bindExerciseData(userId);
    state = UserProfile.fromJson(profileData);
  }

  // ── Register ─────────────────────────────────────────────────────────

  /// Plain sign-up: name, email, password, a goal, and the location consent choice.
  /// No weight, height, or BMI. Signs the player in on success.
  Future<void> register({
    required String email,
    required String password,
    required String displayName,
    required String goal,
    required bool locationConsent,
    String? referralCode,
    String? inviteToken,
  }) async {
    final data = await _api.registerPlayer(
      email: email,
      password: password,
      displayName: displayName,
      goal: goal,
      locationConsent: locationConsent,
      utcOffsetMinutes: localUtcOffsetMinutes(),
      referralCode: referralCode,
      inviteToken: inviteToken,
      installId: ref.read(installIdProvider),
    );
    final token = data['access_token'] as String;
    final userId = (data['profile'] as Map<String, dynamic>)['user_id'] as int;
    await _adoptToken(token, userId);
    await _api.updateMyProfile({'onboarding_completed': true});
  }

  /// Replace the stored token (after sign-up, "sign out everywhere", or a password change).
  Future<void> _adoptToken(String token, int userId) async {
    _api.setToken(token);
    await _storage.write(key: 'auth_token', value: token);
    await _storage.write(key: 'user_id', value: userId.toString());
    await ref.read(runQueueProvider).bindUser(userId);
    _bindExerciseData(userId);
    state = UserProfile.fromJson(await _api.getUserProfile(userId));
  }

  /// Sign out of every other device; this device keeps a fresh token.
  Future<void> signOutEverywhere() async {
    final data = await _api.revokeAllSessions();
    final current = state;
    if (current != null) await _adoptToken(data['access_token'] as String, current.id);
  }

  // ── Logout ───────────────────────────────────────────────────────────

  Future<void> logout() async {
    await ref.read(runQueueProvider).bindUser(null);
    _bindExerciseData(null);
    await _clearCredentials();
    state = null;
  }

  /// Exercise history on this phone belongs to one account at a time, like the run queue.
  void _bindExerciseData(int? userId) {
    unawaited(ref.read(exerciseStoreProvider.future).then((s) => s.forgetOtherUsers(userId)).catchError((_) {}));
  }

  Future<void> _clearCredentials() async {
    _api.setToken(null);
    await _storage.delete(key: 'auth_token');
    await _storage.delete(key: 'user_id');
  }
}

// ── Camera-verified exercises ──────────────────────────────────────────

/// On-device SQLite store: catalog cache, sets and rep timings.
final exerciseStoreProvider = FutureProvider<ExerciseStore>((ref) async {
  final store = await ExerciseStore.open();
  ref.onDispose(store.close);
  return store;
});

/// The catalog the rep engine runs with: cached server copy, else the bundled one. A server
/// refresh runs in the background and applies from the next set on.
final exerciseCatalogProvider = FutureProvider<ExerciseCatalog>((ref) async {
  final repo = CatalogRepository(
    store: await ref.watch(exerciseStoreProvider.future),
    loadBundled: () => rootBundle.loadString('assets/exercise_catalog.json'),
    fetch: ref.read(apiClientProvider).getExerciseCatalog,
  );
  final catalog = await repo.load();
  unawaited(repo.refresh());
  return catalog;
});

/// A fresh pose source per camera session (ML Kit on device; scripted in tests).
final poseSourceFactoryProvider = Provider<PoseSource Function()>((ref) => () => MlKitPoseSource());

final exerciseSyncProvider = FutureProvider<ExerciseSync>((ref) async {
  final store = await ref.watch(exerciseStoreProvider.future);
  return ExerciseSync(store, ref.read(apiClientProvider).submitExerciseSession);
});

/// What happened to a finished set: saved locally, and uploaded if the network allowed.
class SetOutcome {
  final bool uploaded;
  final int xpAwarded;

  const SetOutcome({required this.uploaded, required this.xpAwarded});
}

/// Saves a finished set on the phone, then tries to upload everything pending.
final exerciseRecorderProvider = Provider<Future<SetOutcome> Function(SessionSummary, DateTime)>((ref) {
  return (summary, startedAt) async {
    final user = ref.read(authProvider);
    if (user == null) return const SetOutcome(uploaded: false, xpAwarded: 0);
    final store = await ref.read(exerciseStoreProvider.future);
    await store.saveSession(summary, userId: user.id, startedAt: startedAt);
    final result = await (await ref.read(exerciseSyncProvider.future)).flush(user.id);
    ref.invalidate(exerciseHistoryProvider);
    return SetOutcome(uploaded: !result.offline && result.uploaded > 0, xpAwarded: result.xpAwarded);
  };
});

class ExerciseHistory {
  final List<StoredSession> recent;
  final Map<String, double> bests;

  const ExerciseHistory(this.recent, this.bests);
}

/// Recent sets and personal bests, read from SQLite (instant, offline). Opening it also
/// retries any uploads still pending.
final exerciseHistoryProvider = FutureProvider.autoDispose<ExerciseHistory>((ref) async {
  final user = ref.watch(authProvider);
  if (user == null) return const ExerciseHistory([], {});
  final store = await ref.watch(exerciseStoreProvider.future);
  unawaited(ref.read(exerciseSyncProvider.future).then((s) => s.flush(user.id)).catchError((_) => const SyncResult(0, 0)));
  return ExerciseHistory(await store.recent(user.id), await store.personalBests(user.id));
});
