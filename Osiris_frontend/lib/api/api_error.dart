import 'package:dio/dio.dart';

class ApiError {
  static String getMessage(Object e) {
    if (e is DioException) {
      if (e.response != null) {
        if (e.response?.statusCode == 500) {
          return 'Server error occurred. Please try again later.';
        }
        if (e.response?.data != null && e.response?.data is Map) {
          final data = e.response!.data as Map;
          if (data.containsKey('detail')) {
            return data['detail'].toString();
          }
        }
        return e.message ?? 'Unknown API Error';
      } else if (e.type == DioExceptionType.connectionTimeout || 
                 e.type == DioExceptionType.receiveTimeout || 
                 e.type == DioExceptionType.sendTimeout) {
        return 'Connection timed out. Please check your internet.';
      } else if (e.type == DioExceptionType.connectionError) {
        return 'No internet connection.';
      }
      return e.message ?? 'Network error occurred.';
    }
    return e.toString();
  }
}
