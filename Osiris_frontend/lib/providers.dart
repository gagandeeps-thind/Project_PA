import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api/api_client.dart';
import 'api/models.dart';

// --- Shared Preferences Provider ---
final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('sharedPreferencesProvider must be overridden in main.dart');
});

// --- API Client Provider ---
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(); // Connects to localhost:8000 by default
});

// --- Session Manager / Auth Provider ---
class AuthNotifier extends Notifier<UserProfile?> {
  
  @override
  UserProfile? build() {
    // Delay session load until after initial build to prevent async state mutation during init
    Future.microtask(() => _loadSession());
    return null;
  }

  Future<void> _loadSession() async {
    final prefs = ref.read(sharedPreferencesProvider);
    final userId = prefs.getInt('user_id');
    final token = prefs.getString('access_token');
    
    if (userId != null && token != null) {
      try {
        final client = ref.read(apiClientProvider);
        client.setToken(token);
        final profileData = await client.getUserProfile(userId);
        state = UserProfile.fromJson(profileData);
      } catch (e) {
        // Token/Session expired or network error
        print('Failed to load session: $e');
        await logout();
      }
    } else {
      await logout();
    }
  }

  Future<void> login(String email, String password) async {
    final prefs = ref.read(sharedPreferencesProvider);
    final client = ref.read(apiClientProvider);
    
    final deviceTimestamp = DateTime.now().toUtc().toIso8601String();
    
    final data = await client.loginUser(
      email: email, 
      password: password, 
      deviceTimestamp: deviceTimestamp
    );
    
    final baseProfile = UserProfile.fromJson(data);
    await prefs.setInt('user_id', baseProfile.id);
    
    final token = data['access_token'];
    if (token != null) {
      await prefs.setString('access_token', token);
      client.setToken(token);
    }
    
    if (baseProfile.role == 'player') {
      // The auth endpoint only returns a minimal payload.
      // We must fetch the full player profile for the game UI.
      try {
        final fullProfileData = await client.getUserProfile(baseProfile.id);
        // Merge the role into the full profile data before parsing
        fullProfileData['role'] = baseProfile.role;
        state = UserProfile.fromJson(fullProfileData);
      } catch (e) {
        print('Warning: Failed to fetch full player profile after login: $e');
        state = baseProfile;
      }
    } else {
      // Admins and Merchants don't have full game profiles, the base is enough.
      state = baseProfile;
    }
  }

  Future<void> register(String email, String password, double weightKg, double heightM, String preferredPath) async {
    final client = ref.read(apiClientProvider);
    
    final deviceTimestamp = DateTime.now().toUtc().toIso8601String();
    
    await client.onboardUser(
      email: email, 
      password: password, 
      weightKg: weightKg, 
      heightM: heightM, 
      preferredPath: preferredPath,
      deviceTimestamp: deviceTimestamp
    );
    
    await login(email, password);
  }

  Future<void> logout() async {
    final prefs = ref.read(sharedPreferencesProvider);
    await prefs.remove('user_id');
    await prefs.remove('access_token');
    ref.read(apiClientProvider).setToken(null);
    state = null;
  }
}

final authProvider = NotifierProvider<AuthNotifier, UserProfile?>(() {
  return AuthNotifier();
});
