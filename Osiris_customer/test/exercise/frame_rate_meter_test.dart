import 'package:flutter_test/flutter_test.dart';
import 'package:osiris_customer/exercise/frame_rate_meter.dart';

void main() {
  test('frame rate is measured over a full window, so model warm-up drops out', () {
    final m = FrameRateMeter(window: 5);
    m.add(0);
    m.add(2000); // ML Kit warm-up: the first result arrives seconds later
    expect(m.fps, isNull);
    for (final t in [2100, 2200, 2300]) {
      m.add(t);
    }
    expect(m.fps, closeTo(4 * 1000 / 2300, 0.01), reason: 'the warm-up gap is still in the window');
    m.add(2400);
    expect(m.fps, closeTo(10, 0.01), reason: 'once the gap leaves the window, the real rate shows');
  });

  test('the slow warning has hysteresis and does not flicker at the limit', () {
    final d = SlowTrackingDetector(5);
    expect(d.update(null), isFalse);
    expect(d.update(6), isFalse);
    expect(d.update(4.9), isTrue);
    expect(d.update(5.5), isTrue, reason: 'stays on until 20% above the limit');
    expect(d.update(6.0), isFalse);
  });
}
