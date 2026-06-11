import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'providers.dart';
import 'theme.dart';
import 'screens/login_screen.dart';
import 'screens/merchant_dashboard_screen.dart';
import 'screens/bounty_management_screen.dart';
import 'screens/analytics_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // final prefs = await SharedPreferences.getInstance(); // Not needed if sharedPreferencesProvider doesn't exist

  runApp(
    ProviderScope(
      child: const OsirisMerchantApp(),
    ),
  );
}

class OsirisMerchantApp extends StatelessWidget {
  const OsirisMerchantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Osiris Merchant',
      debugShowCheckedModeBanner: false,
      theme: MerchantTheme.darkTheme,
      home: const AuthWrapper(),
      routes: {
        '/dashboard': (_) => const MerchantDashboardScreen(),
        '/bounties': (_) => const BountyManagementScreen(),
        '/analytics': (_) => const AnalyticsScreen(),
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
      return const MerchantDashboardScreen();
    }

    return const LoginScreen();
  }
}
