import 'dart:async';
import 'dart:math';
import 'package:sensors_plus/sensors_plus.dart';

/// Accelerometer + gyroscope step counter with cadence calculation.
///
/// Uses a rolling window to smooth out noise and detect step peaks
/// from the magnitude of acceleration minus gravity.
class PedometerService {
  int _stepCount = 0;
  double _cadence = 0.0; // steps per minute

  StreamSubscription<UserAccelerometerEvent>? _accelSub;

  // Rolling window for cadence calculation
  final List<DateTime> _stepTimestamps = [];
  static const int _windowSize = 20; // last N steps for cadence

  // Step detection state
  bool _isPeak = false;
  static const double _stepThreshold = 1.8; // m/s² above baseline

  /// Current total step count this session.
  int get stepCount => _stepCount;

  /// Current cadence in steps per minute.
  double get cadence => _cadence;

  /// Start listening to sensor data and counting steps.
  void start({Function(int steps, double cadence)? onStep}) {
    _stepCount = 0;
    _cadence = 0.0;
    _stepTimestamps.clear();

    _accelSub = userAccelerometerEventStream().listen((event) {
      final magnitude = sqrt(
        event.x * event.x + event.y * event.y + event.z * event.z,
      );

      // Simple peak detection
      if (magnitude > _stepThreshold && !_isPeak) {
        _isPeak = true;
        _stepCount++;

        final now = DateTime.now();
        _stepTimestamps.add(now);

        // Trim to rolling window
        if (_stepTimestamps.length > _windowSize) {
          _stepTimestamps.removeAt(0);
        }

        // Calculate cadence from rolling window
        _updateCadence();

        onStep?.call(_stepCount, _cadence);
      } else if (magnitude < _stepThreshold * 0.6) {
        _isPeak = false;
      }

    });
  }

  void _updateCadence() {
    if (_stepTimestamps.length < 2) {
      _cadence = 0.0;
      return;
    }

    final windowDuration = _stepTimestamps.last
        .difference(_stepTimestamps.first)
        .inMilliseconds;

    if (windowDuration <= 0) {
      _cadence = 0.0;
      return;
    }

    final stepsInWindow = _stepTimestamps.length - 1;
    _cadence = (stepsInWindow / windowDuration) * 60000; // per minute
  }

  /// Stop listening and reset.
  void stop() {
    _accelSub?.cancel();
    _accelSub = null;
  }

  /// Dispose resources.
  void dispose() {
    stop();
  }
}
