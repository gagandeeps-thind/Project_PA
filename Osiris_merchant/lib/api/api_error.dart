import 'package:dio/dio.dart';

/// Centralised error message extraction for DioExceptions and generic errors.
class ApiError {
  /// Extracts a user-friendly error message from any exception.
  static String getMessage(dynamic e) {
    if (e is DioException) {
      // Server responded with an error status code
      if (e.response != null) {
        final statusCode = e.response!.statusCode;
        final data = e.response!.data;

        // Try to extract backend "detail" message
        String? detail;
        if (data is Map<String, dynamic>) {
          detail = data['detail']?.toString();
        }

        switch (statusCode) {
          case 401:
            return detail ?? 'Unauthorized. Please log in again.';
          case 403:
            return detail ?? 'Access denied. Merchant privileges required.';
          case 409:
            return detail ?? 'Conflict. This resource already exists.';
          case 422:
            return detail ?? 'Validation error. Please check your input.';
          case 500:
            return 'Server error. Please try again later.';
          default:
            return detail ?? 'Request failed (HTTP $statusCode).';
        }
      }

      // Network-level errors (no response received)
      switch (e.type) {
        case DioExceptionType.connectionTimeout:
          return 'Connection timed out. Check your network.';
        case DioExceptionType.sendTimeout:
          return 'Send timed out. Check your network.';
        case DioExceptionType.receiveTimeout:
          return 'Response timed out. The server may be busy.';
        case DioExceptionType.connectionError:
          return 'Cannot reach the server. Check your connection.';
        case DioExceptionType.cancel:
          return 'Request was cancelled.';
        default:
          return 'Network error: ${e.message}';
      }
    }

    // Generic exceptions
    return e.toString().replaceFirst('Exception: ', '');
  }
}
