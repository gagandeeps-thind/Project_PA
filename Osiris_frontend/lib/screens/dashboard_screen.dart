import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers.dart';
import '../theme.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userProfile = ref.watch(authProvider);

    if (userProfile == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(userProfile.title.toUpperCase()),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: AppTheme.error),
            onPressed: () {
              ref.read(authProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Profile Card
            Card(
              color: AppTheme.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 40,
                      backgroundColor: AppTheme.primary.withOpacity(0.2),
                      child: Icon(
                        userProfile.avatarClass == 'Tank' 
                            ? Icons.shield 
                            : userProfile.avatarClass == 'Assassin' 
                                ? Icons.flash_on 
                                : Icons.auto_fix_high,
                        size: 40,
                        color: AppTheme.primary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      userProfile.rank,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(color: AppTheme.secondary),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${userProfile.xp} XP • ${userProfile.manaCrystals} Crystals',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Class: ${userProfile.avatarClass}',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            // Map / Domain Action
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pushNamed(context, '/map');
              },
              icon: const Icon(Icons.map),
              label: const Text('DOMAIN EXPANSION'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 16),
            // Bounty Board Action
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pushNamed(context, '/bounties');
              },
              icon: const Icon(Icons.explore),
              label: const Text('BOUNTY BOARD'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.surface,
                foregroundColor: AppTheme.primary,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 16),
            // Vault Action
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pushNamed(context, '/vault');
              },
              icon: const Icon(Icons.diamond),
              label: const Text('THE VAULT'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.secondary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 24),
            // Adventure Profile Action
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pushNamed(context, '/profile');
              },
              icon: const Icon(Icons.person),
              label: const Text('ADVENTURE PROFILE'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.surface,
                foregroundColor: AppTheme.primary,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

