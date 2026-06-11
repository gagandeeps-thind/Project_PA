import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api_client.dart';
import 'api/models.dart';

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
    final userId = data['user_id'] as int;

    _api.setToken(token);

    await _storage.write(key: 'auth_token', value: token);
    await _storage.write(key: 'user_id', value: userId.toString());

    // Fetch full profile
    final profileData = await _api.getUserProfile(userId);
    state = UserProfile.fromJson(profileData);
  }

  // ── Register ─────────────────────────────────────────────────────────

  /// Onboard a new player then auto-login.
  Future<void> register(
    String email,
    String password,
    double weightKg,
    double heightM,
    String preferredPath,
  ) async {
    final timestamp = DateTime.now().toUtc().toIso8601String();
    await _api.onboardUser(
      email,
      password,
      weightKg,
      heightM,
      preferredPath,
      timestamp,
    );

    // Auto-login after successful registration
    await login(email, password);
  }

  // ── Logout ───────────────────────────────────────────────────────────

  Future<void> logout() async {
    await _clearCredentials();
    state = null;
  }

  Future<void> _clearCredentials() async {
    _api.setToken(null);
    await _storage.delete(key: 'auth_token');
    await _storage.delete(key: 'user_id');
  }
}
