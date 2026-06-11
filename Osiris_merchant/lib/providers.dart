import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'api/api_client.dart';
import 'api/models.dart';

// ─────────────────────────────────────────────────────
// Infrastructure Providers
// ─────────────────────────────────────────────────────

/// Secure storage for JWT tokens and merchant IDs.
final secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

/// Singleton API client connecting to http://10.0.2.2:8000.
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});

// ─────────────────────────────────────────────────────
// Auth Notifier — manages merchant login/logout/session
// ─────────────────────────────────────────────────────

class AuthNotifier extends Notifier<MerchantProfile?> {
  @override
  MerchantProfile? build() {
    // Restore session from secure storage on startup
    Future.microtask(() => _loadSession());
    return null;
  }

  /// Attempt to restore a previous session from secure storage.
  Future<void> _loadSession() async {
    final secureStorage = ref.read(secureStorageProvider);
    final merchantIdStr = await secureStorage.read(key: 'merchant_id');
    final token = await secureStorage.read(key: 'access_token');

    if (merchantIdStr != null && token != null) {
      final merchantId = int.tryParse(merchantIdStr);
      if (merchantId != null) {
        try {
          final client = ref.read(apiClientProvider);
          client.setToken(token);
          final profileData = await client.getMerchantProfile(merchantId);
          profileData['role'] = 'merchant'; // Ensure role is set
          state = MerchantProfile.fromJson(profileData);
        } catch (e) {
          // Token expired or network error
          print('Failed to restore merchant session: $e');
          await logout();
        }
      } else {
        await logout();
      }
    }
    // If no stored credentials, state remains null (show login screen)
  }

  /// Authenticates a merchant. REJECTS non-merchant roles.
  Future<void> login(String email, String password) async {
    final secureStorage = ref.read(secureStorageProvider);
    final client = ref.read(apiClientProvider);

    final deviceTimestamp = DateTime.now().toUtc().toIso8601String();

    final data = await client.loginMerchant(
      email: email,
      password: password,
      deviceTimestamp: deviceTimestamp,
    );

    // ── CRITICAL: Reject non-merchant roles ──
    final role = data['role'] ?? 'player';
    if (role != 'merchant') {
      throw Exception('This app is for Osiris merchants only.');
    }

    final token = data['access_token'];
    final merchantId = data['merchant_id'] ?? data['id'];

    if (token != null) {
      await secureStorage.write(key: 'access_token', value: token);
      client.setToken(token);
    }

    if (merchantId != null) {
      await secureStorage.write(key: 'merchant_id', value: merchantId.toString());

      // Fetch full merchant profile
      try {
        final profileData = await client.getMerchantProfile(merchantId);
        profileData['role'] = 'merchant';
        state = MerchantProfile.fromJson(profileData);
      } catch (e) {
        // Fallback: build a minimal profile from login data
        print('Warning: Could not fetch full merchant profile: $e');
        state = MerchantProfile.fromJson(data);
      }
    } else {
      state = MerchantProfile.fromJson(data);
    }
  }

  /// Clears all stored credentials and resets state.
  Future<void> logout() async {
    final secureStorage = ref.read(secureStorageProvider);
    await secureStorage.delete(key: 'merchant_id');
    await secureStorage.delete(key: 'access_token');
    ref.read(apiClientProvider).setToken(null);
    state = null;
  }
}

final authProvider = NotifierProvider<AuthNotifier, MerchantProfile?>(() {
  return AuthNotifier();
});

// ─────────────────────────────────────────────────────
// Data Providers
// ─────────────────────────────────────────────────────

/// Fetches the current merchant's profile. Auto-refreshes when auth changes.
final merchantProfileProvider = FutureProvider<MerchantProfile?>((ref) async {
  final auth = ref.watch(authProvider);
  if (auth == null) return null;

  final client = ref.read(apiClientProvider);
  final data = await client.getMerchantProfile(auth.id);
  data['role'] = 'merchant';
  return MerchantProfile.fromJson(data);
});

/// Fetches all bounties belonging to the current merchant.
final merchantBountiesProvider = FutureProvider<List<MerchantBounty>>((ref) async {
  final auth = ref.watch(authProvider);
  if (auth == null) return [];

  final client = ref.read(apiClientProvider);
  final data = await client.getMerchantBounties(auth.id);

  // The API may return { "bounties": [...] } or just a list
  final List<dynamic> bountyList;
  if (data is Map<String, dynamic> && data.containsKey('bounties')) {
    bountyList = data['bounties'] as List<dynamic>;
  } else if (data is Map<String, dynamic> && data.containsKey('items')) {
    bountyList = data['items'] as List<dynamic>;
  } else {
    bountyList = [];
  }

  return bountyList
      .map((b) => MerchantBounty.fromJson(b as Map<String, dynamic>))
      .toList();
});
