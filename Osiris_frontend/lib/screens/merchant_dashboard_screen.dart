import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers.dart';
import '../theme.dart';

class MerchantDashboardScreen extends ConsumerWidget {
  const MerchantDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userProfile = ref.watch(authProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('CLIENT PORTAL'),
        backgroundColor: AppTheme.surface,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: AppTheme.error),
            onPressed: () {
              ref.read(authProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.storefront, size: 80, color: AppTheme.primary),
              const SizedBox(height: 24),
              const Text(
                'Welcome to the Client Portal',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: AppTheme.secondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Logged in as: ${userProfile?.email ?? "Merchant"}',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 48),
              const Card(
                color: AppTheme.surface,
                child: Padding(
                  padding: EdgeInsets.all(24.0),
                  child: Text(
                    'Note: The primary Merchant tools (campaign management, analytics, billing) are located in the Web Portal. \n\nThis mobile view will soon feature QR scanning for coupon redemption and chest placement management.',
                    style: TextStyle(color: Colors.white54, height: 1.5),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
