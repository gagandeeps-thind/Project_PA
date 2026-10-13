import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// Wrapper around [Geolocator] for location access.
class LocationService {
  /// Request permissions and return the current position.
  static Future<Position> getCurrentLocation() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw Exception('Location services are disabled.');
    }

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        throw Exception('Location permission denied.');
      }
    }

    if (permission == LocationPermission.deniedForever) {
      throw Exception(
        'Location permissions are permanently denied. '
        'Please enable them in settings.',
      );
    }

    // Without a time limit this waits forever when there is no fix (indoors, emulator).
    try {
      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
    } on TimeoutException {
      final last = await Geolocator.getLastKnownPosition();
      if (last != null) return last;
      throw Exception('Could not get a GPS fix. Move somewhere with a clear view of the sky and try again.');
    }
  }

  /// Stream of position updates for live tracking.
  ///
  /// While a run is [recording], tracking must survive the screen locking or the app going
  /// to the background, otherwise the route gets a gap and the run is rejected. On Android
  /// that is a foreground service with a visible, ongoing notification (started while the
  /// app is open, so "while in use" permission suffices); on iOS, background location
  /// updates with the system location indicator shown.
  static Stream<Position> getLocationStream({
    int distanceFilter = 5,
    bool recording = false,
  }) {
    final LocationSettings settings;
    if (recording && defaultTargetPlatform == TargetPlatform.android) {
      settings = AndroidSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: distanceFilter,
        foregroundNotificationConfig: const ForegroundNotificationConfig(
          notificationTitle: 'Osiris is recording your run',
          notificationText: 'GPS stays on until you finish. Your route stays private.',
          notificationChannelName: 'Run recording',
          enableWakeLock: true,
          setOngoing: true,
        ),
      );
    } else if (recording && defaultTargetPlatform == TargetPlatform.iOS) {
      settings = AppleSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: distanceFilter,
        activityType: ActivityType.fitness,
        pauseLocationUpdatesAutomatically: false,
        allowBackgroundLocationUpdates: true,
        showBackgroundLocationIndicator: true,
      );
    } else {
      settings = LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: distanceFilter);
    }
    return Geolocator.getPositionStream(locationSettings: settings);
  }

  /// Calculate the distance in meters between two GPS coordinates.
  static double distanceBetween(
    double startLat,
    double startLng,
    double endLat,
    double endLng,
  ) {
    return Geolocator.distanceBetween(startLat, startLng, endLat, endLng);
  }
}
