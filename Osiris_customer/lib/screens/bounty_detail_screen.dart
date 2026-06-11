import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../providers.dart';
import '../services/location_service.dart';
import '../theme.dart';

/// Detailed bounty view with completion button.
class BountyDetailScreen extends ConsumerStatefulWidget {
  const BountyDetailScreen({super.key});

  @override
  ConsumerState<BountyDetailScreen> createState() => _BountyDetailScreenState();
}

class _BountyDetailScreenState extends ConsumerState<BountyDetailScreen> {
  bool _completing = false;

  Future<void> _completeBounty(Map<String, dynamic> bounty) async {
    setState(() => _completing = true);

    try {
      final pos = await LocationService.getCurrentLocation();
      final api = ref.read(apiClientProvider);
      final user = ref.read(authProvider);

      final result = await api.completeBounty(
        bounty['id'] as int,
        {
          'user_id': user?.id,
          'latitude': pos.latitude,
          'longitude': pos.longitude,
          'device_timestamp': DateTime.now().toUtc().toIso8601String(),
        },
      );

      if (mounted) {
        _showSuccessDialog(result);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ApiError.getMessage(e)),
            backgroundColor: OsirisTheme.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _completing = false);
    }
  }

  void _showSuccessDialog(Map<String, dynamic> result) {
    final xp = result['xp_earned'] ?? result['xp_reward'] ?? 0;
    final crystals =
        result['crystals_earned'] ?? result['crystal_reward'] ?? 0;
    final coupon = result['coupon_code'] as String?;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OsirisTheme.surface,
        title: Row(
          children: [
            const Icon(Icons.celebration, color: OsirisTheme.success),
            const SizedBox(width: 8),
            const Text('Bounty Complete!'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('⭐ $xp XP earned'),
            Text('💎 $crystals crystals earned'),
            if (coupon != null) ...[
              const SizedBox(height: 8),
              Text(
                '🎫 Coupon: $coupon',
                style: const TextStyle(
                  color: OsirisTheme.secondary,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ],
        ),
        actions: [
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              Navigator.pop(context);
            },
            child: const Text('CLAIM'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bounty =
        ModalRoute.of(context)!.settings.arguments as Map<String, dynamic>;

    final title = bounty['title'] as String? ?? 'Unknown Bounty';
    final desc = bounty['description'] as String? ?? 'No description';
    final type = bounty['type'] as String? ?? 'quest';
    final targetScore = bounty['target_score'];
    final xpReward = bounty['xp_reward'] ?? 0;
    final crystalReward = bounty['crystal_reward'] ?? 0;

    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Title + Type ──
            Center(
              child: Icon(
                Icons.assignment_turned_in,
                size: 64,
                color: OsirisTheme.primary,
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: OsirisTheme.primary.withAlpha(51),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: OsirisTheme.primary),
                ),
                child: Text(
                  type.toUpperCase(),
                  style: const TextStyle(
                    color: OsirisTheme.primary,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.5,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),

            // ── Description ──
            Text(
              'MISSION BRIEF',
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: OsirisTheme.secondary,
                  ),
            ),
            const SizedBox(height: 8),
            Text(desc, style: const TextStyle(fontSize: 15)),
            const SizedBox(height: 24),

            // ── Target Score ──
            if (targetScore != null) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      const Icon(Icons.track_changes,
                          color: OsirisTheme.secondary),
                      const SizedBox(width: 12),
                      Text(
                        'Target Score: $targetScore',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],

            // ── Rewards ──
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'REWARDS',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: OsirisTheme.secondary,
                          ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Icon(Icons.star, color: OsirisTheme.primary),
                        const SizedBox(width: 8),
                        Text(
                          '$xpReward XP',
                          style: const TextStyle(fontSize: 18),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.diamond,
                            color: OsirisTheme.secondary),
                        const SizedBox(width: 8),
                        Text(
                          '$crystalReward Mana Crystals',
                          style: const TextStyle(fontSize: 18),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),

            // ── Complete Button ──
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _completing ? null : () => _completeBounty(bounty),
                icon: _completing
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.check_circle),
                label: const Text('COMPLETE BOUNTY'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
