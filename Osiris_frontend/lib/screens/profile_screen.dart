import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers.dart';
import '../theme.dart';
import '../api/models.dart';

final partyRoleProvider = FutureProvider<PartyRoleResponse>((ref) async {
  final userProfile = ref.watch(authProvider);
  if (userProfile == null) {
    throw Exception('Not logged in');
  }
  final client = ref.read(apiClientProvider);
  final data = await client.getPartyRole(userProfile.id, windowDays: 30);
  return PartyRoleResponse.fromJson(data);
});

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userProfile = ref.watch(authProvider);
    final partyRoleAsync = ref.watch(partyRoleProvider);

    if (userProfile == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('ADVENTURE PROFILE'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Core Identity Card
            Card(
              color: AppTheme.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 50,
                      backgroundColor: AppTheme.primary.withOpacity(0.2),
                      child: Icon(
                        userProfile.avatarClass == 'Tank'
                            ? Icons.shield
                            : userProfile.avatarClass == 'Assassin'
                                ? Icons.flash_on
                                : Icons.auto_fix_high,
                        size: 50,
                        color: AppTheme.primary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      userProfile.title.toUpperCase(),
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: AppTheme.secondary,
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${userProfile.rank} • Class: ${userProfile.avatarClass}',
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${userProfile.xp} XP • ${userProfile.manaCrystals} Crystals',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Streak: ${userProfile.streak} Days',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: AppTheme.success,
                          ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'PARTY ROLE (30-DAY ROLLING)',
              style: TextStyle(
                color: AppTheme.secondary,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            // Party Role Card
            partyRoleAsync.when(
              data: (roleData) {
                return Card(
                  color: AppTheme.surface,
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      children: [
                        Text(
                          roleData.role.toUpperCase(),
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                color: AppTheme.primary,
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                        const SizedBox(height: 8),
                        Text('Leading Stat: ${roleData.leadingStat}'),
                        const SizedBox(height: 16),
                        GridView.count(
                          crossAxisCount: 2,
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          childAspectRatio: 2.5,
                          mainAxisSpacing: 8,
                          crossAxisSpacing: 8,
                          children: [
                            _StatTile('STR', roleData.strStat, Colors.redAccent),
                            _StatTile('AGI', roleData.agiStat, Colors.orangeAccent),
                            _StatTile('END', roleData.endStat, Colors.blueAccent),
                            _StatTile('CON', roleData.conStat, Colors.greenAccent),
                          ],
                        )
                      ],
                    ),
                  ),
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, stack) => Text('Error loading role: $err', style: const TextStyle(color: AppTheme.error)),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final int value;
  final Color color;

  const _StatTile(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3), width: 1),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 16)),
          Text(value.toString(), style: const TextStyle(color: AppTheme.textPrimary, fontSize: 18, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
