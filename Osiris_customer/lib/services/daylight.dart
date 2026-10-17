import 'dart:math' as math;

/// Sun position for the low-light run warning (Security plan §3: show lighting warnings based on
/// available context). Pure Dart, computed on the phone from the current fix: no network call
/// and the location never leaves the device.
///
/// Uses the NOAA solar position equations (accurate to about a minute, far finer than this
/// warning needs).
class Daylight {
  /// Civil twilight ends when the sun is 6 degrees below the horizon; after that, streets
  /// without lighting are effectively dark.
  static const darkBelowDegrees = -6.0;

  /// Solar elevation in degrees at [when] (any time zone) for [lat], [lng].
  static double sunElevation(DateTime when, double lat, double lng) {
    final t = when.toUtc();
    final dayOfYear = t.difference(DateTime.utc(t.year)).inDays + 1;
    final hour = t.hour + t.minute / 60 + t.second / 3600;
    // Fractional year in radians.
    final g = 2 * math.pi / 365 * (dayOfYear - 1 + (hour - 12) / 24);
    final eqTime = 229.18 *
        (0.000075 +
            0.001868 * math.cos(g) -
            0.032077 * math.sin(g) -
            0.014615 * math.cos(2 * g) -
            0.040849 * math.sin(2 * g));
    final decl = 0.006918 -
        0.399912 * math.cos(g) +
        0.070257 * math.sin(g) -
        0.006758 * math.cos(2 * g) +
        0.000907 * math.sin(2 * g) -
        0.002697 * math.cos(3 * g) +
        0.00148 * math.sin(3 * g);
    final trueSolarMinutes = hour * 60 + eqTime + 4 * lng;
    final hourAngle = (trueSolarMinutes / 4 - 180) * math.pi / 180;
    final latR = lat * math.pi / 180;
    final cosZenith = math.sin(latR) * math.sin(decl) + math.cos(latR) * math.cos(decl) * math.cos(hourAngle);
    return 90 - math.acos(cosZenith.clamp(-1.0, 1.0)) * 180 / math.pi;
  }

  /// True when the sun is below civil twilight at [when] for [lat], [lng].
  static bool isDark(DateTime when, double lat, double lng) => sunElevation(when, lat, lng) < darkBelowDegrees;
}
