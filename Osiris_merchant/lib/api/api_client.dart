import 'package:dio/dio.dart';

/// Self-contained Dio-based API client for the Osiris Merchant Portal.
/// Connects to the backend at http://10.0.2.2:8000 (Android emulator localhost).
class ApiClient {
  late final Dio _dio;
  String? _accessToken;

  void Function()? onUnauthorized;

  ApiClient({
    String baseUrl = const String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000'),
    this.onUnauthorized,
  }) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
      headers: {
        'Content-Type': 'application/json',
      },
    ));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_accessToken != null) {
          options.headers['Authorization'] = 'Bearer $_accessToken';
        }
        return handler.next(options);
      },
      onError: (DioException error, handler) {
        if (error.response?.statusCode == 401) {
          onUnauthorized?.call();
        }
        return handler.next(error);
      },
    ));
  }

  /// Sets the JWT access token for authenticated requests.
  void setToken(String? token) {
    _accessToken = token;
  }

  Dio get dio => _dio;

  // ──────────────────────────────────────────────
  // Auth
  // ──────────────────────────────────────────────

  /// Authenticates a merchant via email/password.
  /// Returns the login payload including `access_token`, `role`, `merchant_id`.
  Future<Map<String, dynamic>> loginMerchant({
    required String email,
    required String password,
    required String deviceTimestamp,
  }) async {
    final response = await _dio.post('/api/v1/auth/login', data: {
      'email': email,
      'password': password,
      'device_timestamp': deviceTimestamp,
    });
    return response.data;
  }

  // ──────────────────────────────────────────────
  // Merchant Profile
  // ──────────────────────────────────────────────

  /// Fetches the full merchant profile by ID.
  Future<Map<String, dynamic>> getMerchantProfile(int merchantId) async {
    final response = await _dio.get('/api/v1/merchants/$merchantId');
    return response.data;
  }

  // ──────────────────────────────────────────────
  // Bounties
  // ──────────────────────────────────────────────

  /// Lists all bounties belonging to this merchant.
  Future<Map<String, dynamic>> getMerchantBounties(int merchantId) async {
    final response = await _dio.get('/api/v1/merchants/$merchantId/bounties');
    return response.data;
  }

  /// Creates a new merchant_chest bounty.
  Future<Map<String, dynamic>> createBounty(Map<String, dynamic> data) async {
    final payload = Map<String, dynamic>.from(data);
    payload['bounty_type'] = 'merchant_chest';
    payload['device_timestamp'] = DateTime.now().toUtc().toIso8601String();
    final response = await _dio.post('/api/v1/bounties', data: payload);
    return response.data;
  }

  // ──────────────────────────────────────────────
  // Payments
  // ──────────────────────────────────────────────

  /// Creates a payment intent for the merchant pilot fee.
  Future<Map<String, dynamic>> createPaymentIntent(int merchantId) async {
    final response = await _dio.post('/api/v1/merchants/$merchantId/payments/intent');
    return response.data;
  }

  /// Simulates a payment webhook for MVP testing.
  Future<Map<String, dynamic>> simulatePaymentWebhook({
    required int merchantId,
    required String providerPaymentId,
    required String status,
  }) async {
    final response = await _dio.post('/api/v1/payments/webhook', data: {
      'merchant_id': merchantId,
      'provider_payment_id': providerPaymentId,
      'status': status,
    });
    return response.data;
  }

  // ──────────────────────────────────────────────
  // Coupons
  // ──────────────────────────────────────────────

  /// Redeems a coupon by its code.
  Future<Map<String, dynamic>> redeemCoupon(String couponCode) async {
    final response = await _dio.post('/api/v1/coupons/$couponCode/redeem');
    return response.data;
  }
}
