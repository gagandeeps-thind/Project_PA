import 'package:dio/dio.dart';

/// Self-contained Dio-based API client for the Osiris backend.
/// Connects to the local dev server at http://10.0.2.2:8000 (Android emulator).
class ApiClient {
  static const String _baseUrl = 'http://10.0.2.2:8000';

  final Dio _dio;
  String? _token;

  ApiClient()
      : _dio = Dio(
          BaseOptions(
            baseUrl: _baseUrl,
            connectTimeout: const Duration(seconds: 15),
            receiveTimeout: const Duration(seconds: 15),
            headers: {'Content-Type': 'application/json'},
          ),
        ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          if (_token != null) {
            options.headers['Authorization'] = 'Bearer $_token';
          }
          return handler.next(options);
        },
      ),
    );
  }

  /// Set or clear the JWT auth token.
  void setToken(String? token) {
    _token = token;
  }

  // ── Auth ──────────────────────────────────────────────────────────────

  /// Login with email + password. Returns the raw response data map.
  Future<Map<String, dynamic>> loginUser(
    String email,
    String password,
    String deviceTimestamp,
  ) async {
    final response = await _dio.post(
      '/api/v1/auth/login',
      data: {
        'email': email,
        'password': password,
        'device_timestamp': deviceTimestamp,
      },
    );
    return response.data as Map<String, dynamic>;
  }

  /// Onboard (register) a new player account.
  Future<Map<String, dynamic>> onboardUser(
    String email,
    String password,
    double weightKg,
    double heightM,
    String preferredPath,
    String deviceTimestamp,
  ) async {
    final response = await _dio.post(
      '/api/v1/onboard',
      data: {
        'email': email,
        'password': password,
        'weight_kg': weightKg,
        'height_m': heightM,
        'preferred_path': preferredPath,
        'device_timestamp': deviceTimestamp,
      },
    );
    return response.data as Map<String, dynamic>;
  }

  // ── Users ─────────────────────────────────────────────────────────────

  /// Fetch a full user profile by ID.
  Future<Map<String, dynamic>> getUserProfile(int userId) async {
    final response = await _dio.get('/api/v1/users/$userId');
    return response.data as Map<String, dynamic>;
  }

  /// Get the computed party role for a user.
  Future<Map<String, dynamic>> getPartyRole(
    int userId, {
    int? windowDays,
  }) async {
    final queryParams = <String, dynamic>{};
    if (windowDays != null) {
      queryParams['window_days'] = windowDays;
    }
    final response = await _dio.get(
      '/api/v1/users/$userId/party-role',
      queryParameters: queryParams,
    );
    return response.data as Map<String, dynamic>;
  }

  // ── Domains ───────────────────────────────────────────────────────────

  /// Submit a new domain polygon. Automatically adds device_timestamp.
  Future<Map<String, dynamic>> submitDomain(
    Map<String, dynamic> data,
  ) async {
    final payload = {
      ...data,
      'device_timestamp': DateTime.now().toUtc().toIso8601String(),
    };
    final response = await _dio.post('/api/v1/domains', data: payload);
    return response.data as Map<String, dynamic>;
  }

  /// Fetch domains near a GPS coordinate.
  Future<List<dynamic>> getNearbyDomains(
    double lat,
    double lng,
    double radiusKm,
  ) async {
    final response = await _dio.get(
      '/api/v1/domains/nearby',
      queryParameters: {'lat': lat, 'lng': lng, 'radius_km': radiusKm},
    );
    return response.data as List<dynamic>;
  }

  // ── Bounties ──────────────────────────────────────────────────────────

  /// Fetch bounties near a GPS coordinate.
  Future<List<dynamic>> getNearbyBounties(
    double lat,
    double lng,
    double radiusKm,
  ) async {
    final response = await _dio.get(
      '/api/v1/bounties/nearby',
      queryParameters: {'lat': lat, 'lng': lng, 'radius_km': radiusKm},
    );
    return response.data as List<dynamic>;
  }

  /// Complete a bounty challenge.
  Future<Map<String, dynamic>> completeBounty(
    int bountyId,
    Map<String, dynamic> data,
  ) async {
    final response = await _dio.post(
      '/api/v1/bounties/$bountyId/complete',
      data: data,
    );
    return response.data as Map<String, dynamic>;
  }
}
