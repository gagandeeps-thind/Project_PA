import 'package:dio/dio.dart';

class ApiClient {
  late final Dio _dio;

  ApiClient({String baseUrl = 'http://10.0.2.2:8000'}) {
    // 10.0.2.2 is standard for Android Emulator to hit localhost
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {
        'Content-Type': 'application/json',
      },
    ));
  }

  Dio get dio => _dio;

  // Epic 1: Onboarding / Login

  Future<Map<String, dynamic>> onboardUser({
    required String email,
    required String password,
    required double weightKg,
    required double heightM,
    required String preferredPath,
    required String deviceTimestamp,
  }) async {
    final response = await _dio.post('/api/v1/onboard', data: {
      'email': email,
      'password': password,
      'weight_kg': weightKg,
      'height_m': heightM,
      'preferred_path': preferredPath,
      'device_timestamp': deviceTimestamp,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> loginUser({
    required String email,
    required String password,
    required String deviceTimestamp,
  }) async {
    final response = await _dio.post('/api/v1/login', data: {
      'email': email,
      'password': password,
      'device_timestamp': deviceTimestamp,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> getUserProfile(int userId) async {
    final response = await _dio.get('/api/v1/users/$userId');
    return response.data;
  }

  // Epic 4 & 5: Domains and Sieges
  
  Future<Map<String, dynamic>> submitDomain(Map<String, dynamic> data) async {
    final response = await _dio.post('/api/v1/domains', data: data);
    return response.data;
  }
  
  Future<Map<String, dynamic>> getNearbyBounties({
    required double lat,
    required double lng,
    double radiusKm = 5.0,
  }) async {
    final response = await _dio.get('/api/v1/bounties/nearby', queryParameters: {
      'lat': lat,
      'lng': lng,
      'radius_km': radiusKm,
    });
    return response.data; // This is a list in practice
  }

  Future<Map<String, dynamic>> completeBounty(int bountyId, Map<String, dynamic> data) async {
    final response = await _dio.post('/api/v1/bounties/$bountyId/complete', data: data);
    return response.data;
  }
}
