import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:osiris_customer/api/challenge_models.dart';

void main() {
  test('challenge payload parses generalized marker and free entry', () {
    final c = ChallengeSummary.fromJson({
      'id': 7,
      'title': 'Beat my straight',
      'status': 'open',
      'course_distance_m': 1200.0,
      'target_seconds': 400.0,
      'entry_crystals': 0,
      'reward_policy': 'xp_badge',
      'win_xp': 62,
      'participation_xp': 10,
      'closes_at': '2030-01-01T00:00:00',
      'marker_lat': 44.7025,
      'marker_lng': -63.4975,
      'attempt_count': 2,
      'is_mine': false,
      'my_attempt': null,
      'terms_hash': 'abc',
    });
    expect(c.entryCrystals, 0);
    expect(c.marker, const LatLng(44.7025, -63.4975));
    expect(c.myAttempt, isNull);
  });

  test('reason codes and durations render for people', () {
    expect(explainReason('ROUTE_OFF_COURSE'), contains('off the course'));
    expect(explainReason('SOMETHING_NEW'), 'SOMETHING_NEW');
    expect(formatDuration(400), '6:40');
    expect(formatDuration(3725), '1:02:05');
    expect(formatDistance(1234), '1.23 km');
  });
}
