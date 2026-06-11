import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../providers.dart';
import '../theme.dart';

/// Main dashboard showing player profile card and navigation buttons.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  /// Pick avatar icon based on class.
  IconData _avatarIcon(String avatarClass) {
    switch (avatarClass.toLowerCase()) {
      case 'warrior':
        return Icons.shield;
      case 'rogue':
      case 'ranger':
        return Icons.flash_on;
      case 'mage':
        return Icons.auto_fix_high;
      default:
        return Icons.person;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider);

    if (user == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('OSIRIS'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // ── Profile Card ──
            _ProfileCard(user: user, avatarIcon: _avatarIcon(user.avatarClass)),
            const SizedBox(height: 24),

            // ── Navigation Grid ──
            _NavButton(
              icon: Icons.map,
              label: 'DOMAIN EXPANSION',
              color: OsirisTheme.primary,
              onTap: () => Navigator.of(context).pushNamed('/map'),
            ),
            const SizedBox(height: 12),
            _NavButton(
              icon: Icons.assignment,
              label: 'BOUNTY BOARD',
              color: OsirisTheme.secondary,
              onTap: () => Navigator.of(context).pushNamed('/bounties'),
            ),
            const SizedBox(height: 12),
            _NavButton(
              icon: Icons.account_balance,
              label: 'THE VAULT',
              color: const Color(0xFFFDD835),
              onTap: () => Navigator.of(context).pushNamed('/vault'),
            ),
            const SizedBox(height: 12),
            _NavButton(
              icon: Icons.person,
              label: 'ADVENTURE PROFILE',
              color: OsirisTheme.success,
              onTap: () => Navigator.of(context).pushNamed('/profile'),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Profile Card Widget ────────────────────────────────────────────────

class _ProfileCard extends StatelessWidget {
  final UserProfile user;
  final IconData avatarIcon;

  const _ProfileCard({required this.user, required this.avatarIcon});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            // Avatar + Class
            Row(
              children: [
                CircleAvatar(
                  radius: 32,
                  backgroundColor: OsirisTheme.primary.withAlpha(51),
                  child: Icon(avatarIcon, size: 36, color: OsirisTheme.primary),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        user.title,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${user.avatarClass.toUpperCase()} • ${user.rank}',
                        style: TextStyle(
                          color: OsirisTheme.secondary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            const Divider(color: Colors.white24),
            const SizedBox(height: 12),

            // Stats row
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _StatChip(
                  icon: Icons.star,
                  label: 'XP',
                  value: user.xp.toString(),
                  color: OsirisTheme.primary,
                ),
                _StatChip(
                  icon: Icons.diamond,
                  label: 'Crystals',
                  value: user.manaCrystals.toString(),
                  color: OsirisTheme.secondary,
                ),
                _StatChip(
                  icon: Icons.local_fire_department,
                  label: 'Streak',
                  value: '${user.streak}d',
                  color: Colors.orange,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatChip({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 24),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.bold,
            fontSize: 18,
          ),
        ),
        Text(
          label,
          style: const TextStyle(color: Colors.white60, fontSize: 11),
        ),
      ],
    );
  }
}

// ── Navigation Button Widget ──────────────────────────────────────────

class _NavButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _NavButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: onTap,
        icon: Icon(icon, color: color),
        label: Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.5,
          ),
        ),
        style: OutlinedButton.styleFrom(
          side: BorderSide(color: color.withAlpha(128)),
          padding: const EdgeInsets.symmetric(vertical: 18),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
    );
  }
}
