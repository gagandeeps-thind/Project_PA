import 'package:dio/dio.dart';

/// Self-contained Dio-based API client for the Osiris backend.
/// Connects to the local dev server at http://10.0.2.2:8000 (Android emulator).
class ApiClient {
  static const String _baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');

  final Dio _dio;
  String? _token;
  void Function()? onUnauthorized;

  ApiClient({this.onUnauthorized})
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
        onError: (DioException error, handler) {
          if (error.response?.statusCode == 401) {
            onUnauthorized?.call();
          }
          return handler.next(error);
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

  // ── Verified running ─────────────────────────────────────────────────────

  Future<Map<String, dynamic>> createRun({
    String activityType = 'run',
    required String deviceStartedAt,
  }) async {
    final response = await _dio.post('/api/v2/runs', data: {
      'activity_type': activityType,
      'device_started_at': deviceStartedAt,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> startRun(
    int runId,
    String deviceStartedAt,
  ) async {
    final response = await _dio.post('/api/v2/runs/$runId/start', data: {
      'device_started_at': deviceStartedAt,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> appendRunPoints(
    int runId,
    List<Map<String, dynamic>> points,
  ) async {
    final response = await _dio.post('/api/v2/runs/$runId/points', data: {
      'points': points,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> finishRun(
    int runId,
    String deviceFinishedAt,
    String idempotencyKey,
  ) async {
    final response = await _dio.post('/api/v2/runs/$runId/finish', data: {
      'device_finished_at': deviceFinishedAt,
      'idempotency_key': idempotencyKey,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getRun(int runId) async {
    final response = await _dio.get('/api/v2/runs/$runId');
    return response.data as Map<String, dynamic>;
  }

  // ── Courses & challenges (R2) ───────────────────────────────────────────

  Future<Map<String, dynamic>> registerCourse(int runId, String name) async {
    final response = await _dio.post('/api/v2/courses', data: {
      'run_id': runId,
      'name': name,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> getMyCourses() async {
    final response = await _dio.get('/api/v2/courses');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> publishChallenge({
    required int courseId,
    required String title,
    required int windowHours,
    String? safetyNotes,
    required String idempotencyKey,
  }) async {
    final response = await _dio.post('/api/v2/challenges', data: {
      'course_id': courseId,
      'title': title,
      'window_hours': windowHours,
      if (safetyNotes != null && safetyNotes.isNotEmpty) 'safety_notes': safetyNotes,
      'idempotency_key': idempotencyKey,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> getNearbyChallenges(
    double lat,
    double lng,
    double radiusKm,
  ) async {
    final response = await _dio.get(
      '/api/v2/challenges/nearby',
      queryParameters: {'lat': lat, 'lng': lng, 'radius_km': radiusKm},
    );
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getChallenge(int challengeId) async {
    final response = await _dio.get('/api/v2/challenges/$challengeId');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getChallengeCourse(int challengeId) async {
    final response = await _dio.get('/api/v2/challenges/$challengeId/course');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> joinChallenge(int challengeId) async {
    final response = await _dio.post('/api/v2/challenges/$challengeId/join');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> submitAttempt(int challengeId, int runId) async {
    final response = await _dio.post(
      '/api/v2/challenges/$challengeId/attempts',
      data: {'run_id': runId},
    );
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getProgression() async {
    final response = await _dio.get('/api/v2/me/progression');
    return response.data as Map<String, dynamic>;
  }

  // ── Growth: registration, profile, today ─────────────────────────────────

  /// BMI-free registration. Returns {access_token, profile}.
  Future<Map<String, dynamic>> registerPlayer({
    required String email,
    required String password,
    required String displayName,
    required String goal,
    required bool locationConsent,
    required int utcOffsetMinutes,
    String? referralCode,
    String? inviteToken,
    String? installId,
  }) async {
    final response = await _dio.post('/api/v2/auth/register', data: {
      'email': email,
      'password': password,
      'display_name': displayName,
      'goal': goal,
      'location_consent': locationConsent,
      'utc_offset_minutes': utcOffsetMinutes,
      if (referralCode != null && referralCode.isNotEmpty) 'referral_code': referralCode,
      if (inviteToken != null && inviteToken.isNotEmpty) 'invite_token': inviteToken,
      'install_id': ?installId,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getMyProfile() async {
    final response = await _dio.get('/api/v2/me/profile');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateMyProfile(Map<String, dynamic> changes) async {
    final response = await _dio.put('/api/v2/me/profile', data: changes);
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getToday({double? lat, double? lng, int? utcOffsetMinutes}) async {
    final response = await _dio.get('/api/v2/me/today', queryParameters: {
      'lat': ?lat,
      'lng': ?lng,
      'utc_offset_minutes': ?utcOffsetMinutes,
    });
    return response.data as Map<String, dynamic>;
  }

  /// Fire-and-forget funnel event. Never throws.
  Future<void> trackEvent(String name, {String? installId, Map<String, dynamic>? properties}) async {
    try {
      await _dio.post('/api/v2/events', data: {
        'event_name': name,
        'install_id': ?installId,
        'properties': properties ?? {},
      });
    } catch (_) {}
  }

  // ── Growth: sharing, invites, referrals ─────────────────────────────────

  Future<Map<String, dynamic>> createShareCard(String kind, int entityId) async {
    final response = await _dio.post('/api/v2/share', data: {'kind': kind, 'entity_id': entityId});
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createChallengeInvite(int challengeId) async {
    final response = await _dio.post('/api/v2/challenges/$challengeId/invites');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getReferrals() async {
    final response = await _dio.get('/api/v2/me/referrals');
    return response.data as Map<String, dynamic>;
  }

  // ── Growth: communities, rankings, seasons ──────────────────────────────

  Future<List<dynamic>> getCommunities({String? city}) async {
    final response = await _dio.get('/api/v2/communities', queryParameters: {'city': ?city});
    return response.data as List<dynamic>;
  }

  Future<List<dynamic>> getMyCommunities() async {
    final response = await _dio.get('/api/v2/me/communities');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getCommunity(String slug) async {
    final response = await _dio.get('/api/v2/communities/$slug');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> joinCommunity(String slug, {String? joinCode}) async {
    final response = await _dio.post('/api/v2/communities/$slug/join', data: {
      if (joinCode != null && joinCode.isNotEmpty) 'join_code': joinCode,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<void> leaveCommunity(String slug) async {
    await _dio.post('/api/v2/communities/$slug/leave');
  }

  Future<Map<String, dynamic>> getCommunityLeaderboard(String slug) async {
    final response = await _dio.get('/api/v2/communities/$slug/leaderboard');
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> getCommunityChallenges(String slug) async {
    final response = await _dio.get('/api/v2/communities/$slug/challenges');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getLocalLeaderboard() async {
    final response = await _dio.get('/api/v2/leaderboards/local');
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> getSeasons() async {
    final response = await _dio.get('/api/v2/seasons');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> joinSeason(String slug) async {
    final response = await _dio.post('/api/v2/seasons/$slug/join');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSeasonLeaderboard(String slug) async {
    final response = await _dio.get('/api/v2/seasons/$slug/leaderboard');
    return response.data as Map<String, dynamic>;
  }

  // ── Growth: safety, privacy, account ───────────────────────────────────

  Future<Map<String, dynamic>> report({
    required String targetType,
    int? targetId,
    String? targetRef,
    required String reason,
    String? details,
  }) async {
    final response = await _dio.post('/api/v2/reports', data: {
      'target_type': targetType,
      'target_id': ?targetId,
      'target_ref': ?targetRef,
      'reason': reason,
      if (details != null && details.isNotEmpty) 'details': details,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> blockChallengeCreator(int challengeId) async {
    final response = await _dio.post('/api/v2/blocks', data: {'challenge_id': challengeId});
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> getBlocks() async {
    final response = await _dio.get('/api/v2/me/blocks');
    return response.data as List<dynamic>;
  }

  Future<void> unblock(int blockId) async {
    await _dio.delete('/api/v2/blocks/$blockId');
  }

  Future<Map<String, dynamic>> revokeAllSessions() async {
    final response = await _dio.post('/api/v2/me/sessions/revoke');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> exportMyData() async {
    final response = await _dio.get('/api/v2/me/export');
    return response.data as Map<String, dynamic>;
  }

  Future<void> eraseMyAccount(String password) async {
    await _dio.post('/api/v2/me/erase', data: {'password': password, 'confirm': 'DELETE'});
  }

  Future<Map<String, dynamic>> getRules() async {
    final response = await _dio.get('/api/v2/rules');
    return response.data as Map<String, dynamic>;
  }

  // ── Domains (legacy) ─────────────────────────────────────────────────

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
