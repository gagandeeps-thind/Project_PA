import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'providers.dart';
import 'theme.dart';
import 'screens/login_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/map_screen.dart';
import 'screens/bounty_board_screen.dart';
import 'screens/challenge_board_screen.dart';
import 'screens/challenge_detail_screen.dart';
import 'screens/my_courses_screen.dart';
import 'screens/bounty_detail_screen.dart';
import 'screens/vault_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/today_screen.dart';
import 'screens/communities_screen.dart';
import 'screens/rankings_screen.dart';
import 'screens/settings_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: const OsirisCustomerApp(),
    ),
  );
}

class OsirisCustomerApp extends StatelessWidget {
  const OsirisCustomerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Osiris',
      debugShowCheckedModeBanner: false,
      theme: OsirisTheme.darkTheme,
      // Android 15+ draws apps edge-to-edge; keep every screen's content and buttons clear of
      // the gesture bar instead of padding each scroll view separately.
      builder: (context, child) => SafeArea(top: false, left: false, right: false, child: child!),
      home: const AuthWrapper(),
      routes: {
        '/onboard': (_) => const OnboardingScreen(),
        '/dashboard': (_) => const DashboardScreen(),
        '/map': (_) => const MapScreen(),
        '/challenges': (_) => const ChallengeBoardScreen(),
        '/challenge': (_) => const ChallengeDetailScreen(),
        '/courses': (_) => const MyCoursesScreen(),
        '/bounties': (_) => const BountyBoardScreen(),
        '/bounty-detail': (_) => const BountyDetailScreen(),
        '/vault': (_) => const VaultScreen(),
        '/profile': (_) => const ProfileScreen(),
        '/today': (_) => const TodayScreen(),
        '/communities': (_) => const CommunitiesScreen(),
        '/rankings': (_) => const RankingsScreen(),
        '/settings': (_) => const SettingsScreen(),
      },
    );
  }
}

/// Root wrapper: today's quest when signed in, sign-in otherwise.
class AuthWrapper extends ConsumerWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider);

    if (user != null) {
      return const TodayScreen();
    }

    return const LoginScreen();
  }
}
