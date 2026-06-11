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
import 'screens/bounty_detail_screen.dart';
import 'screens/vault_screen.dart';
import 'screens/profile_screen.dart';

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
      home: const AuthWrapper(),
      routes: {
        '/onboard': (_) => const OnboardingScreen(),
        '/dashboard': (_) => const DashboardScreen(),
        '/map': (_) => const MapScreen(),
        '/bounties': (_) => const BountyBoardScreen(),
        '/bounty-detail': (_) => const BountyDetailScreen(),
        '/vault': (_) => const VaultScreen(),
        '/profile': (_) => const ProfileScreen(),
      },
    );
  }
}

/// Root wrapper that shows Dashboard if logged in, Login otherwise.
class AuthWrapper extends ConsumerWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider);

    if (user != null) {
      return const DashboardScreen();
    }

    return const LoginScreen();
  }
}
