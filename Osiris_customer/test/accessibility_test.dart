// Accessibility audit (PRD non-functional requirements: large touch targets, readable
// controls, non-colour-only status). Each main screen is rendered with the real theme and
// checked against Flutter's built-in guidelines: Android tap-target size (48x48 dp), labelled
// tap targets for screen readers, and WCAG AA text contrast.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:osiris_customer/api/api_client.dart';
import 'package:osiris_customer/api/growth_models.dart';
import 'package:osiris_customer/providers.dart';
import 'package:osiris_customer/screens/challenge_detail_screen.dart';
import 'package:osiris_customer/screens/exercise_hub_screen.dart';
import 'package:osiris_customer/screens/login_screen.dart';
import 'package:osiris_customer/screens/my_courses_screen.dart';
import 'package:osiris_customer/screens/onboarding_screen.dart';
import 'package:osiris_customer/screens/settings_screen.dart';
import 'package:osiris_customer/screens/today_screen.dart';
import 'package:osiris_customer/theme.dart';

import 'exercise/pose_synth.dart';

class _QuietApi extends ApiClient {
  @override
  Future<void> trackEvent(String name, {String? installId, Map<String, dynamic>? properties}) async {}

  @override
  Future<Map<String, dynamic>> getMyProfile() async => {
        'user_id': 7, 'display_name': 'Ada', 'goal': 'running', 'identity': 'runner',
        'public_profile': false, 'location_consent': true, 'onboarding_completed': true,
        'referral_code': 'ADA12345', 'city': 'Halifax', 'leaderboard_opt_in': true,
      };

  @override
  Future<Map<String, dynamic>> getReferrals() async =>
      {'referral_code': 'ADA12345', 'url': 'https://osiris.example/join/ADA12345', 'pending': 0, 'rewarded': 1, 'rules': []};

  @override
  Future<List<dynamic>> getMyCourses() async => [
        {
          'id': 3, 'name': 'Common North Straight', 'status': 'active', 'distance_m': 965.0,
          'benchmark_seconds': 323.0, 'is_loop': false, 'route': [[44.6, -63.6], [44.61, -63.6]],
          'open_challenge_id': null,
        },
      ];

  @override
  Future<Map<String, dynamic>> getChallenge(int challengeId) async => {
        'id': challengeId, 'title': 'Beat my Common North Straight', 'status': 'open', 'course_distance_m': 965.0,
        'target_seconds': 323.0, 'entry_crystals': 0, 'reward_policy': 'xp_badge', 'win_xp': 59,
        'participation_xp': 10, 'safety_notes': 'Shared path with cyclists; keep right.',
        'closes_at': '2030-01-01T00:00:00', 'marker_lat': 44.6525, 'marker_lng': -63.5825, 'attempt_count': 1,
        'is_mine': false, 'my_attempt': null, 'terms_hash': 'abc',
      };
}

Map<String, dynamic> _quest(String kind, String title) => {
      'key': 'daily:2026-10-14',
      'kind': kind,
      'title': title,
      'description': 'Walking counts.',
      'target_m': 1000,
      'xp': 25,
      'optional': false,
      'progress_m': 400.0,
      'completed': false,
      'rewarded': false,
    };

TodayData _today() => TodayData.fromJson({
      'tagline': 'Fitness, turned into quests.',
      'display_name': 'Ada',
      'identity': 'runner',
      'goal': 'running',
      'xp': 40,
      'performance_rank': 'Bronze',
      'rules_version': 'quest-rules-v1',
      'today': _quest('starter', 'Walk or run 1 km'),
      'tomorrow': _quest('steady', 'Move 1.2 km'),
      'week': {
        'key': 'weekly:2026-W42',
        'week_start': '2026-10-12',
        'active_days_target': 3,
        'active_days': 1,
        'distance_m': 1200.0,
        'xp': 50,
        'completed': false,
        'rewarded': false,
      },
      'streak_weeks': 2,
      'starter_challenge': null,
      'safety_note': 'Go at a pace where you can still talk.',
      'needs_location_consent': false,
    });

Future<Widget> _app(Widget home, {Object? arguments}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final catalog = loadCatalog();
  return ProviderScope(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      apiClientProvider.overrideWithValue(_QuietApi()),
      todayProvider.overrideWith((ref) async => _today()),
      exerciseCatalogProvider.overrideWith((ref) async => catalog),
      exerciseHistoryProvider.overrideWith((ref) async => const ExerciseHistory([], {})),
    ],
    // Screens that read their route argument need it on the initial route's settings.
    child: MaterialApp(
      theme: OsirisTheme.darkTheme,
      onGenerateRoute: (_) => MaterialPageRoute(settings: RouteSettings(name: '/', arguments: arguments), builder: (_) => home),
    ),
  );
}

/// [mustShow] proves the screen rendered its real content; a spinner or error state would
/// otherwise pass the guidelines trivially.
Future<void> _audit(WidgetTester tester, Widget screen, String mustShow, {Object? arguments}) async {
  final handle = tester.ensureSemantics();
  // A phone-width viewport tall enough that lazily built lists render every item; with the
  // default 800x600 surface, content below the fold was never built and never checked.
  tester.view.physicalSize = const Size(412 * 3, 2600 * 3);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(await _app(screen, arguments: arguments));
  await tester.pumpAndSettle();
  expect(find.textContaining(mustShow), findsWidgets);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
  handle.dispose();
}

void main() {
  testWidgets('home (today) screen meets accessibility guidelines', (t) => _audit(t, const TodayScreen(), 'Walk or run 1 km'));
  testWidgets('sign-up screen meets accessibility guidelines', (t) => _audit(t, const OnboardingScreen(), 'Run more'));
  testWidgets('login screen meets accessibility guidelines', (t) => _audit(t, const LoginScreen(), 'LOGIN'));
  testWidgets('exercise hub meets accessibility guidelines', (t) => _audit(t, const ExerciseHubScreen(), 'Push-up'));
  testWidgets('settings screen meets accessibility guidelines', (t) => _audit(t, const SettingsScreen(), 'ADA12345'));
  testWidgets('my courses screen meets accessibility guidelines', (t) => _audit(t, const MyCoursesScreen(), 'Common North Straight'));
  testWidgets('sign-up steps 2 and 3 meet accessibility guidelines', (tester) async {
    await _audit(tester, const OnboardingScreen(), 'Run more');
    final handle = tester.ensureSemantics();
    for (final step in ['Your location, your control', 'START MY FIRST QUEST']) {
      await tester.tap(find.text('CONTINUE'));
      await tester.pumpAndSettle();
      expect(find.textContaining(step), findsWidgets);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
    }
    handle.dispose();
  });
  testWidgets('challenge detail meets accessibility guidelines',
      (t) => _audit(t, const ChallengeDetailScreen(), 'JOIN CHALLENGE', arguments: 7));
}
