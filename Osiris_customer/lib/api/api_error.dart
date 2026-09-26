import 'package:dio/dio.dart';

/// Utility class for extracting human-readable error messages from API responses.
class ApiError {
  /// The v2 error `code` (e.g. `CHALLENGE_NOT_OPEN`) if the server sent one.
  static String? getCode(dynamic e) {
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['detail'] is Map) {
        return (data['detail'] as Map)['code'] as String?;
      }
    }
    return null;
  }

  /// Whether the request never reached the server (safe to retry later).
  static bool isOffline(dynamic e) {
    return e is DioException &&
        (e.type == DioExceptionType.connectionError ||
            e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.sendTimeout ||
            e.type == DioExceptionType.receiveTimeout);
  }

  /// Extract a user-friendly error message from any exception.
  static String getMessage(dynamic e) {
    if (e is DioException) {
      // Connection & timeout errors
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.sendTimeout ||
          e.type == DioExceptionType.receiveTimeout) {
        return 'Connection timed out. Please check your network and try again.';
      }

      if (e.type == DioExceptionType.connectionError) {
        return 'Unable to connect to the server. Please check your internet connection.';
      }

      // Server responded with an error status
      final response = e.response;
      if (response != null) {
        final data = response.data;
        final statusCode = response.statusCode ?? 0;

        // Try to extract detail from response body
        String? detail;
        if (data is Map<String, dynamic>) {
          final raw = data['detail'];
          if (raw is String) {
            detail = raw;
          } else if (raw is Map) {
            // v2 structured errors: {"code": "...", "message": "..."}
            detail = raw['message'] as String? ?? raw['code'] as String?;
          }
          detail ??= data['message'] as String? ?? data['error'] as String?;
          // Handle FastAPI validation errors (422)
          if (detail == null && raw is List) {
            final errors = data['detail'] as List;
            detail = errors
                .map((e) => e is Map ? (e['msg'] ?? e.toString()) : e.toString())
                .join('; ');
          }
        } else if (data is String && data.isNotEmpty) {
          detail = data;
        }

        switch (statusCode) {
          case 401:
            return detail ?? 'Unauthorized. Please log in again.';
          case 403:
            return detail ?? 'Access denied. You do not have permission.';
          case 409:
            return detail ?? 'Conflict. This resource already exists.';
          case 422:
            return detail ?? 'Invalid input. Please check your data.';
          case 500:
            return 'Server error. Please try again later.';
          default:
            return detail ?? 'Request failed (status $statusCode).';
        }
      }

      return 'Network error. Please try again.';
    }

    if (e is Exception) {
      final msg = e.toString();
      // Strip "Exception: " prefix if present
      if (msg.startsWith('Exception: ')) {
        return msg.substring(11);
      }
      return msg;
    }

    return 'An unexpected error occurred.';
  }
}
