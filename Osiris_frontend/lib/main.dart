import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'theme.dart';
import 'providers.dart';
import 'screens/login_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/map_screen.dart';
import 'screens/bounty_board_screen.dart';
import 'screens/bounty_detail_screen.dart';
import 'screens/vault_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/admin_dashboard_screen.dart';
import 'screens/merchant_dashboard_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  final sharedPreferences = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
      ],
      child: const OsirisApp(),
    ),
  );
}

class OsirisApp extends ConsumerWidget {
  const OsirisApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp(
      title: 'Osiris',
      theme: AppTheme.darkTheme,
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      routes: {
        '/': (context) => const AuthWrapper(),
        '/login': (context) => const LoginScreen(),
        '/onboard': (context) => const OnboardingScreen(),
        '/dashboard': (context) => const DashboardScreen(),
        '/map': (context) => const MapScreen(),
        '/bounties': (context) => const BountyBoardScreen(),
        '/bounty_detail': (context) => const BountyDetailScreen(),
        '/vault': (context) => const VaultScreen(),
        '/profile': (context) => const ProfileScreen(),
        '/admin': (context) => const AdminDashboardScreen(),
        '/merchant': (context) => const MerchantDashboardScreen(),
      },
    );
  }
}

class AuthWrapper extends ConsumerWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userProfile = ref.watch(authProvider);

    if (userProfile == null) {
      return const LoginScreen();
    } else {
      if (userProfile.role == 'admin') {
        return const AdminDashboardScreen();
      } else if (userProfile.role == 'merchant') {
        return const MerchantDashboardScreen();
      } else {
        return const DashboardScreen();
      }
    }
  }
}
