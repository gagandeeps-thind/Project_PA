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
class AuthNotifier extends StateNotifier<UserProfile?> {
  final Ref ref;
  
  AuthNotifier(this.ref) : super(null) {
    _loadSession();
  }

  Future<void> _loadSession() async {
    final prefs = ref.read(sharedPreferencesProvider);
    final userId = prefs.getInt('user_id');
    if (userId != null) {
      try {
        final profileData = await ref.read(apiClientProvider).getUserProfile(userId);
        state = UserProfile.fromJson(profileData);
      } catch (e) {
        // Token/Session expired or network error
        print('Failed to load session: $e');
        await logout();
      }
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
    
    final profile = UserProfile.fromJson(data);
    await prefs.setInt('user_id', profile.id);
    state = profile;
  }

  Future<void> register(String email, String password, double weightKg, double heightM, String preferredPath) async {
    final prefs = ref.read(sharedPreferencesProvider);
    final client = ref.read(apiClientProvider);
    
    final deviceTimestamp = DateTime.now().toUtc().toIso8601String();
    
    final data = await client.onboardUser(
      email: email, 
      password: password, 
      weightKg: weightKg, 
      heightM: heightM, 
      preferredPath: preferredPath,
      deviceTimestamp: deviceTimestamp
    );
    
    final profile = UserProfile.fromJson(data);
    await prefs.setInt('user_id', profile.id);
    state = profile;
  }

  Future<void> logout() async {
    final prefs = ref.read(sharedPreferencesProvider);
    await prefs.remove('user_id');
    state = null;
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, UserProfile?>((ref) {
  return AuthNotifier(ref);
});
