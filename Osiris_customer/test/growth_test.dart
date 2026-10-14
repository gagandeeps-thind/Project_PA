import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:osiris_customer/api/api_client.dart';
import 'package:osiris_customer/api/growth_models.dart';
import 'package:osiris_customer/providers.dart';
import 'package:osiris_customer/screens/onboarding_screen.dart';
import 'package:osiris_customer/screens/today_screen.dart';

class _QuietApi extends ApiClient {
  final List<String> events = [];

  @override
  Future<void> trackEvent(String name, {String? installId, Map<String, dynamic>? properties}) async {
    events.add(name);
  }
}

Map<String, dynamic> _quest(String kind, String title, {double progress = 0, bool completed = false}) => {
      'key': 'daily:2026-09-28',
      'kind': kind,
      'title': title,
      'description': 'Walking counts.',
      'target_m': 1000,
      'xp': 25,
      'optional': kind == 'recovery',
      'progress_m': progress,
      'completed': completed,
      'rewarded': completed,
    };

Map<String, dynamic> _today({bool consent = false, Map<String, dynamic>? starter}) => {
      'tagline': 'Fitness, turned into quests.',
      'display_name': 'Ada',
      'identity': 'runner',
      'goal': 'running',
      'xp': 40,
      'performance_rank': 'Bronze',
      'rules_version': 'quest-rules-v1',
      'today': _quest('starter', 'Walk or run 1 km', progress: 400),
      'tomorrow': _quest('steady', 'Move 1.2 km'),
      'week': {
        'key': 'weekly:2026-W40',
        'week_start': '2026-09-28',
        'active_days_target': 3,
        'active_days': 1,
        'distance_m': 1200.0,
        'xp': 50,
        'completed': false,
        'rewarded': false,
      },
      'streak_weeks': 2,
      'starter_challenge': starter,
      'safety_note': 'Go at a pace where you can still talk.',
      'needs_location_consent': consent,
    };

Future<Widget> _app(Widget home, {TodayData? today, _QuietApi? api}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      apiClientProvider.overrideWithValue(api ?? _QuietApi()),
      if (today != null) todayProvider.overrideWith((ref) async => today),
    ],
    child: MaterialApp(home: home),
  );
}

void main() {
  test('today payload parses quest progress, week, and streak', () {
    final t = TodayData.fromJson(_today());
    expect(t.today.kind, 'starter');
    expect(t.today.fraction, closeTo(0.4, 1e-9));
    expect(t.week.activeDays, 1);
    expect(t.streakWeeks, 2);
    expect(t.needsLocationConsent, isFalse);
  });

  test('distance labels stay short', () {
    expect(kmLabel(400), '0.4 km');
    expect(kmLabel(12500), '13 km');
  });

  testWidgets('today screen answers "what is my next quest?"', (tester) async {
    final api = _QuietApi();
    await tester.pumpWidget(await _app(const TodayScreen(),
        today: TodayData.fromJson(_today(starter: {
          'id': 9, 'title': 'Harbour Mile', 'course_distance_m': 1600.0, 'distance_km': 0.8,
        })),
        api: api));
    await tester.pumpAndSettle();
    expect(find.text('YOUR FIRST QUEST'), findsOneWidget);
    expect(find.text('Walk or run 1 km'), findsOneWidget);
    expect(find.text('START'), findsOneWidget);
    expect(find.text('2 week streak'), findsOneWidget);
    expect(find.textContaining('Rest days never break your streak'), findsOneWidget);
    expect(find.text('Move 1.2 km'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Harbour Mile'), 200);
    expect(find.text('Harbour Mile'), findsOneWidget);
    expect(find.text('Allow location during runs'), findsNothing);
    expect(api.events, contains('app_opened'));
  });

  testWidgets('today screen asks for location consent when it is missing', (tester) async {
    await tester.pumpWidget(await _app(const TodayScreen(), today: TodayData.fromJson(_today(consent: true))));
    await tester.pumpAndSettle();
    expect(find.text('Allow location during runs'), findsOneWidget);
  });

  testWidgets('onboarding asks for a goal, not body measurements', (tester) async {
    await tester.pumpWidget(await _app(const OnboardingScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Run more'), findsOneWidget);
    expect(find.textContaining('weight', findRichText: true), findsNothing);
    expect(find.textContaining('BMI'), findsNothing);
    await tester.tap(find.text('Compete'));
    await tester.tap(find.text('CONTINUE'));
    await tester.pumpAndSettle();
    expect(find.text('Allow location during runs'), findsOneWidget);
    // Consent is an affirmative choice: the switch must start off, never pre-ticked.
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    await tester.tap(find.text('CONTINUE'));
    await tester.pumpAndSettle();
    expect(find.text('START MY FIRST QUEST'), findsOneWidget);
    expect(find.text('Invite code (optional)'), findsOneWidget);
  });
}
