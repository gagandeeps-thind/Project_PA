import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../providers.dart';
import '../theme.dart';

/// Full adventure profile with stats, party role, rank, title, and streak.
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  PartyRoleResponse? _partyRole;
  bool _loadingRole = true;

  @override
  void initState() {
    super.initState();
    _fetchPartyRole();
  }

  Future<void> _fetchPartyRole() async {
    final user = ref.read(authProvider);
    if (user == null) return;

    try {
      final api = ref.read(apiClientProvider);
      final data = await api.getPartyRole(user.id);
      setState(() {
        _partyRole = PartyRoleResponse.fromJson(data);
        _loadingRole = false;
      });
    } catch (e) {
      setState(() => _loadingRole = false);
      // Non-critical — just show stats without party role
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);

    if (user == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final maxStat = [user.strStat, user.agiStat, user.endStat, user.conStat]
        .reduce((a, b) => a > b ? a : b)
        .clamp(1, 999);

    return Scaffold(
      appBar: AppBar(title: const Text('ADVENTURE PROFILE')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // ── Avatar + Title ──
            CircleAvatar(
              radius: 40,
              backgroundColor: OsirisTheme.primary.withAlpha(51),
              child: Icon(
                _avatarIcon(user.avatarClass),
                size: 44,
                color: OsirisTheme.primary,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              user.title,
              style: Theme.of(context)
                  .textTheme
                  .headlineMedium
                  ?.copyWith(color: OsirisTheme.primary),
            ),
            const SizedBox(height: 4),
            Text(
              '${user.avatarClass.toUpperCase()} • ${user.rank}',
              style: TextStyle(
                color: OsirisTheme.secondary,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),

            // ── Quick Stats ──
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _QuickStat(
                      label: 'XP',
                      value: user.xp.toString(),
                      icon: Icons.star,
                      color: OsirisTheme.primary,
                    ),
                    _QuickStat(
                      label: 'Streak',
                      value: '${user.streak}d',
                      icon: Icons.local_fire_department,
                      color: Colors.orange,
                    ),
                    _QuickStat(
                      label: 'Area',
                      value: '${user.cumulativeArea.toStringAsFixed(1)} km²',
                      icon: Icons.square_foot,
                      color: OsirisTheme.secondary,
                    ),
                    _QuickStat(
                      label: 'Crystals',
                      value: user.manaCrystals.toString(),
                      icon: Icons.diamond,
                      color: OsirisTheme.secondary,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Stat Bars ──
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'COMBAT STATS',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: OsirisTheme.secondary,
                          ),
                    ),
                    const SizedBox(height: 16),
                    _StatBar(
                      label: 'STR',
                      value: user.strStat,
                      max: maxStat,
                      color: OsirisTheme.strColor,
                    ),
                    const SizedBox(height: 12),
                    _StatBar(
                      label: 'AGI',
                      value: user.agiStat,
                      max: maxStat,
                      color: OsirisTheme.agiColor,
                    ),
                    const SizedBox(height: 12),
                    _StatBar(
                      label: 'END',
                      value: user.endStat,
                      max: maxStat,
                      color: OsirisTheme.endColor,
                    ),
                    const SizedBox(height: 12),
                    _StatBar(
                      label: 'CON',
                      value: user.conStat,
                      max: maxStat,
                      color: OsirisTheme.conColor,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Party Role ──
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'PARTY ROLE',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: OsirisTheme.secondary,
                          ),
                    ),
                    const SizedBox(height: 12),
                    if (_loadingRole)
                      const Center(
                        child: SizedBox(
                          height: 24,
                          width: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    else if (_partyRole != null)
                      Row(
                        children: [
                          Icon(
                            _roleIcon(_partyRole!.role),
                            size: 36,
                            color: OsirisTheme.primary,
                          ),
                          const SizedBox(width: 12),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _partyRole!.role.toUpperCase(),
                                style: const TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                  color: OsirisTheme.primary,
                                ),
                              ),
                              Text(
                                'Leading stat: ${_partyRole!.leadingStat.toUpperCase()}',
                                style: const TextStyle(color: Colors.white60),
                              ),
                            ],
                          ),
                        ],
                      )
                    else
                      const Text(
                        'Complete more activities to unlock your party role!',
                        style: TextStyle(color: Colors.white54),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

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

  IconData _roleIcon(String role) {
    switch (role.toLowerCase()) {
      case 'tank':
        return Icons.shield;
      case 'healer':
        return Icons.healing;
      case 'dps':
        return Icons.flash_on;
      case 'support':
        return Icons.group;
      default:
        return Icons.person;
    }
  }
}

// ── Stat Bar Widget ──────────────────────────────────────────────────────

class _StatBar extends StatelessWidget {
  final String label;
  final int value;
  final int max;
  final Color color;

  const _StatBar({
    required this.label,
    required this.value,
    required this.max,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final ratio = max > 0 ? (value / max).clamp(0.0, 1.0) : 0.0;

    return Row(
      children: [
        SizedBox(
          width: 36,
          child: Text(
            label,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: 13,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: ratio,
              backgroundColor: color.withAlpha(38),
              valueColor: AlwaysStoppedAnimation(color),
              minHeight: 10,
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 32,
          child: Text(
            value.toString(),
            textAlign: TextAlign.right,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }
}

// ── Quick Stat Widget ────────────────────────────────────────────────────

class _QuickStat extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _QuickStat({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.bold,
            fontSize: 14,
          ),
        ),
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 10),
        ),
      ],
    );
  }
}
