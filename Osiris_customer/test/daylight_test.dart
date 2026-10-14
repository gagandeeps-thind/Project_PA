import 'package:flutter_test/flutter_test.dart';

import 'package:osiris_customer/services/daylight.dart';

void main() {
  const halifax = (44.65, -63.58);
  const tromso = (69.65, 18.96);

  test('solar noon elevation matches 90 - latitude +/- solstice tilt', () {
    // Halifax solar noon is about 16:15 UTC. Summer: 90 - 44.65 + 23.44 = 68.8.
    expect(Daylight.sunElevation(DateTime.utc(2026, 6, 21, 16, 15), halifax.$1, halifax.$2), closeTo(68.8, 1.0));
    // Winter: 90 - 44.65 - 23.44 = 21.9.
    expect(Daylight.sunElevation(DateTime.utc(2026, 12, 21, 16, 15), halifax.$1, halifax.$2), closeTo(21.9, 1.0));
    // Equator at the March equinox: the sun is nearly overhead at noon.
    expect(Daylight.sunElevation(DateTime.utc(2026, 3, 20, 12, 7), 0, 0), greaterThan(88));
  });

  test('matches a published sunrise (Halifax, 14 Oct 2026, 07:22 ADT)', () {
    // At official sunrise the sun's centre is 0.833 degrees below the horizon.
    expect(Daylight.sunElevation(DateTime.utc(2026, 10, 14, 10, 22), halifax.$1, halifax.$2), closeTo(-0.83, 1.0));
  });

  test('night and day in Halifax', () {
    expect(Daylight.isDark(DateTime.utc(2026, 6, 21, 5), halifax.$1, halifax.$2), isTrue, reason: '01:00 ADT');
    expect(Daylight.isDark(DateTime.utc(2026, 12, 21, 22), halifax.$1, halifax.$2), isTrue, reason: '18:00 AST');
    expect(Daylight.isDark(DateTime.utc(2026, 12, 21, 16), halifax.$1, halifax.$2), isFalse, reason: 'winter noon');
    expect(Daylight.isDark(DateTime.utc(2026, 6, 21, 23), halifax.$1, halifax.$2), isFalse, reason: '20:00 ADT, before dusk');
  });

  test('polar day and polar night', () {
    // Midnight sun: still above the horizon at local midnight in June.
    expect(Daylight.sunElevation(DateTime.utc(2026, 6, 21, 22, 45), tromso.$1, tromso.$2), greaterThan(0));
    expect(Daylight.isDark(DateTime.utc(2026, 6, 21, 22, 45), tromso.$1, tromso.$2), isFalse);
    // Polar night: below the horizon even at noon, and dark by early afternoon.
    expect(Daylight.sunElevation(DateTime.utc(2026, 12, 21, 10, 45), tromso.$1, tromso.$2), lessThan(0));
    expect(Daylight.isDark(DateTime.utc(2026, 12, 21, 14), tromso.$1, tromso.$2), isTrue);
  });

  test('local and UTC timestamps for the same instant agree', () {
    final utc = DateTime.utc(2026, 9, 1, 3, 30);
    expect(Daylight.sunElevation(utc.toLocal(), halifax.$1, halifax.$2),
        closeTo(Daylight.sunElevation(utc, halifax.$1, halifax.$2), 1e-9));
  });
}
